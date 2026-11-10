"""Anagrafiche: vendor, supplier, agenti, mapping, utenti. Lettura: tutti; scrittura: ADMIN."""
from typing import Type

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import schemas as s
from app.db import get_db
from app.models import AppUser, Supplier, UserRole, Vendor, VendorSupplierMap
from app.access import is_staff
from app.security import current_user, require_admin

router = APIRouter(dependencies=[Depends(current_user)])


def _commit(db: Session):
    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(409, f"Vincolo violato: {str(e.orig).splitlines()[0]}")


def crud(path: str, model: Type, in_schema, out_schema):
    @router.get(f"/{path}", response_model=list[out_schema], name=f"list_{path}")
    def list_(active_only: bool = False, db: Session = Depends(get_db)):
        q = select(model).order_by(model.id)
        if active_only:
            q = q.where(model.is_active)
        return db.scalars(q).all()

    @router.post(f"/{path}", response_model=out_schema, status_code=201, name=f"create_{path}",
                 dependencies=[Depends(require_admin)])
    def create(body: in_schema, db: Session = Depends(get_db)):
        obj = model(**body.model_dump())
        db.add(obj)
        _commit(db)
        return obj

    @router.put(f"/{path}/{{obj_id}}", response_model=out_schema, name=f"update_{path}",
                dependencies=[Depends(require_admin)])
    def update_(obj_id: int, body: in_schema, db: Session = Depends(get_db)):
        obj = db.get(model, obj_id)
        if not obj:
            raise HTTPException(404)
        for k, v in body.model_dump().items():
            setattr(obj, k, v)
        _commit(db)
        return obj


crud("vendors", Vendor, s.VendorIn, s.VendorOut)
crud("suppliers", Supplier, s.SupplierIn, s.SupplierOut)


# ----- agenti commerciali = utenti con ruolo SALES (si creano dalla pagina Utenti) -----
@router.get("/agents", response_model=list[s.AgentOut])
def list_agents(db: Session = Depends(get_db), user: AppUser = Depends(current_user)):
    q = select(AppUser).where(AppUser.role == UserRole.SALES, AppUser.is_active).order_by(AppUser.full_name)
    if not is_staff(user):                 # un SALES vede solo se stesso
        q = q.where(AppUser.id == user.id)
    return db.scalars(q).all()


# ----- mapping vendor <-> supplier -----
def _redact(m: VendorSupplierMap, user: AppUser) -> s.MapOut:
    """Il SALES sa quali supplier sono mappati, ma non gli indirizzi dei vendor."""
    out = s.MapOut.model_validate(m)
    if not is_staff(user):
        out.to_emails, out.cc_emails = [], []
    return out


@router.get("/vendor-supplier-map", response_model=list[s.MapOut])
def list_map(vendor_id: int | None = None, db: Session = Depends(get_db),
             user: AppUser = Depends(current_user)):
    q = select(VendorSupplierMap).order_by(VendorSupplierMap.id)
    if vendor_id:
        q = q.where(VendorSupplierMap.vendor_id == vendor_id)
    return [_redact(m, user) for m in db.scalars(q).all()]


@router.put("/vendor-supplier-map", response_model=s.MapOut, dependencies=[Depends(require_admin)])
def upsert_map(body: s.MapIn, db: Session = Depends(get_db)):
    obj = db.scalar(select(VendorSupplierMap).where(
        VendorSupplierMap.vendor_id == body.vendor_id,
        VendorSupplierMap.supplier_id == body.supplier_id))
    if body.is_preferred:     # un solo preferito per vendor
        db.execute(update(VendorSupplierMap)
                   .where(VendorSupplierMap.vendor_id == body.vendor_id).values(is_preferred=False))
    if obj is None:
        obj = VendorSupplierMap(vendor_id=body.vendor_id, supplier_id=body.supplier_id)
        db.add(obj)
    for k in ("to_emails", "cc_emails", "supports_dr", "is_preferred"):
        setattr(obj, k, getattr(body, k))
    _commit(db)
    return obj


@router.delete("/vendor-supplier-map/{map_id}", status_code=204, dependencies=[Depends(require_admin)])
def delete_map(map_id: int, db: Session = Depends(get_db)):
    obj = db.get(VendorSupplierMap, map_id)
    if not obj:
        raise HTTPException(404)
    db.delete(obj)
    _commit(db)


@router.get("/vendors/{vendor_id}/suppliers", response_model=list[s.MapOut])
def vendor_suppliers(vendor_id: int, db: Session = Depends(get_db), user: AppUser = Depends(current_user)):
    rows = db.scalars(select(VendorSupplierMap).where(VendorSupplierMap.vendor_id == vendor_id)).all()
    return [_redact(m, user) for m in rows]
