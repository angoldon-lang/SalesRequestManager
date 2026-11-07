from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import schemas as s
from app.db import get_db
from app.models import InboundEmail, InboundStatus, Request
from app.security import current_user
from app.services.inbound_service import process_row
from app.services.llm_parser import get_parser
from app.services.request_service import get_config

router = APIRouter(prefix="/inbound", dependencies=[Depends(current_user)])


def _row(db: Session, iid: int) -> InboundEmail:
    r = db.get(InboundEmail, iid)
    if not r:
        raise HTTPException(404)
    return r


@router.get("", response_model=list[s.InboundOut])
def list_inbound(status: InboundStatus | None = None, limit: int = 100, db: Session = Depends(get_db)):
    q = select(InboundEmail).order_by(InboundEmail.received_at.desc()).limit(limit)
    if status:
        q = q.where(InboundEmail.status == status)
    return db.scalars(q).all()


@router.post("/{iid}/reprocess", response_model=s.InboundOut)
def reprocess(iid: int, db: Session = Depends(get_db)):
    row = _row(db, iid)
    if db.scalar(select(Request.id).where(Request.inbound_email_id == iid)):
        raise HTTPException(409, "Esiste già una richiesta collegata a questa email")
    row.error_message = None
    process_row(db, row, get_parser(), get_config(db).llm_model)
    db.commit()
    return row


@router.post("/{iid}/ignore", response_model=s.InboundOut)
def ignore(iid: int, db: Session = Depends(get_db)):
    row = _row(db, iid)
    row.status = InboundStatus.IGNORED
    db.commit()
    return row
