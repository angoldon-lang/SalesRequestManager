from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import schemas as s
from app.db import get_db
from app.models import (
    AppUser, Request, RequestEvent, RequestSource, RequestStatus, RequestType, UserRole,
)
from app.access import can_see, is_staff, request_scope
from app.security import current_user
from app.services import request_service as svc
from app.services.graph_client import get_graph
from app.services.reminder_service import send_reminder

router = APIRouter(prefix="/requests", dependencies=[Depends(current_user)])
_graph = None


def graph():
    global _graph
    if _graph is None:
        _graph = get_graph()
    return _graph


def out(r: Request) -> s.RequestOut:
    o = s.RequestOut.model_validate(r)
    o.vendor_name = r.vendor.name if r.vendor else None
    o.supplier_name = r.supplier.name if r.supplier else None
    o.agent_name = r.sales_agent.full_name if r.sales_agent else None
    return o


def load(db: Session, rid: int, user: AppUser) -> Request:
    r = db.get(Request, rid)
    if not r or not can_see(user, r):   # 404 anche se esiste: non rivelare richieste altrui
        raise HTTPException(404, "Richiesta non trovata")
    return r


def commit(db: Session):
    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(422, f"Dati non validi: {str(e.orig).splitlines()[0]}")


@router.get("", response_model=s.RequestPage)
def list_requests(
    status: RequestStatus | None = None, type: RequestType | None = None,
    vendor_id: int | None = None, agent_id: int | None = None,
    date_from: date | None = Query(None, alias="from"), date_to: date | None = Query(None, alias="to"),
    q: str | None = None, needs_review: bool | None = None,
    limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
    db: Session = Depends(get_db), user: AppUser = Depends(current_user),
):
    cond = []
    scope = request_scope(user)
    if scope is not None:
        cond.append(scope)
    if status: cond.append(Request.status == status)
    if type: cond.append(Request.request_type == type)
    if vendor_id: cond.append(Request.vendor_id == vendor_id)
    if agent_id: cond.append(Request.sales_agent_id == agent_id)
    if date_from: cond.append(Request.created_at >= date_from)
    if date_to: cond.append(Request.created_at < date_to + timedelta(days=1))
    if needs_review is not None: cond.append(Request.needs_review == needs_review)
    if q:
        like = f"%{q}%"
        cond.append(or_(Request.subject.ilike(like), Request.code.ilike(like),
                        Request.end_customer_name.ilike(like)))
    total = db.scalar(select(func.count()).select_from(Request).where(*cond))
    rows = db.scalars(select(Request).where(*cond).order_by(Request.created_at.desc(), Request.id.desc())
                      .limit(limit).offset(offset)).unique().all()
    return {"items": [out(r) for r in rows], "total": total}


@router.post("", response_model=s.RequestOut, status_code=201)
def create_request(body: s.RequestCreate, db: Session = Depends(get_db),
                   user: AppUser = Depends(current_user)):
    data = body.model_dump(exclude_none=True)
    if not is_staff(user):                      # il SALES crea sempre a nome proprio
        if user.sales_agent_id is None:
            raise HTTPException(403, "Il tuo utente non è collegato a un agente commerciale: contatta l'admin")
        data["sales_agent_id"] = user.sales_agent_id
    r = Request(**data, status=RequestStatus.DRAFT, source=RequestSource.MANUAL, created_by=user.id)
    db.add(r)
    commit(db)
    svc.add_event(db, r, "CREATED", user.email)
    commit(db)
    return out(r)


@router.get("/{rid}", response_model=s.RequestOut)
def get_request(rid: int, db: Session = Depends(get_db), user: AppUser = Depends(current_user)):
    return out(load(db, rid, user))


EDITABLE_WHEN_SENT = {"end_customer_name", "estimated_deal_value", "expected_close_date",
                      "vendor_dr_reference", "dr_approved_at", "dr_expires_at",
                      "product_description", "quantity", "needs_review"}


@router.patch("/{rid}", response_model=s.RequestOut)
def patch_request(rid: int, body: s.RequestPatch, db: Session = Depends(get_db),
                  user: AppUser = Depends(current_user)):
    r = load(db, rid, user)
    data = body.model_dump(exclude_unset=True)
    if not is_staff(user) and data.get("sales_agent_id", user.sales_agent_id) != user.sales_agent_id:
        raise HTTPException(403, "Non puoi assegnare la richiesta ad un altro agente")
    if r.status == RequestStatus.CLOSED:
        raise HTTPException(409, "Richiesta chiusa: riaprila per modificarla")
    if r.status != RequestStatus.DRAFT:
        locked = set(data) - EDITABLE_WHEN_SENT
        if locked:
            raise HTTPException(409, f"Campi non modificabili dopo l'invio: {sorted(locked)}")
    for k, v in data.items():
        setattr(r, k, v)
    if r.status != RequestStatus.DRAFT:
        miss = svc.missing_dr_fields(r)
        if miss:
            db.rollback()
            raise HTTPException(422, {"message": "Campi DR obbligatori",
                                      "fields": {f: "Obbligatorio per le richieste DR" for f in miss}})
    elif "needs_review" not in data:
        r.needs_review = False        # l'operatore ha rivisto la bozza
    svc.add_event(db, r, "EDITED", user.email, {"fields": sorted(data)})
    commit(db)
    return out(r)


@router.delete("/{rid}", status_code=204)
def delete_request(rid: int, db: Session = Depends(get_db), user: AppUser = Depends(current_user)):
    r = load(db, rid, user)
    if r.status != RequestStatus.DRAFT:
        raise HTTPException(409, "Solo le bozze si possono eliminare")
    db.delete(r)
    commit(db)


@router.post("/{rid}/send", response_model=s.RequestOut)
def send(rid: int, db: Session = Depends(get_db), user: AppUser = Depends(current_user)):
    r = load(db, rid, user)
    svc.send_request(db, graph(), r, user.email)
    commit(db)
    return out(r)


@router.post("/{rid}/remind", response_model=s.RequestOut)
def remind(rid: int, db: Session = Depends(get_db), user: AppUser = Depends(current_user)):
    r = load(db, rid, user)
    if r.status not in (RequestStatus.SENT, RequestStatus.REMINDED):
        raise HTTPException(409, "Reminder possibile solo su richieste inviate")
    send_reminder(db, graph(), svc.get_config(db), r, actor=user.email)
    commit(db)
    return out(r)


@router.post("/{rid}/close", response_model=s.RequestOut)
def close(rid: int, body: s.CloseIn, db: Session = Depends(get_db),
          user: AppUser = Depends(current_user)):
    r = load(db, rid, user)
    svc.close_request(db, r, body.reason, user.email, body.vendor_dr_reference,
                      body.dr_approved_at, body.dr_expires_at)
    commit(db)
    return out(r)


@router.post("/{rid}/reopen", response_model=s.RequestOut)
def reopen(rid: int, db: Session = Depends(get_db), user: AppUser = Depends(current_user)):
    r = load(db, rid, user)
    svc.reopen_request(db, r, user.email)
    commit(db)
    return out(r)


@router.get("/{rid}/events", response_model=list[s.EventOut])
def events(rid: int, db: Session = Depends(get_db), user: AppUser = Depends(current_user)):
    load(db, rid, user)
    return db.scalars(select(RequestEvent).where(RequestEvent.request_id == rid)
                      .order_by(RequestEvent.created_at, RequestEvent.id)).all()
