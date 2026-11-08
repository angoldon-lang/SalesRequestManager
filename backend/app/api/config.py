from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import schemas as s
from app.db import get_db
from app.models import AppUser, GlobalConfig
from app.access import require_staff
from app.security import require_admin
from app.services.request_service import now
from app.api.requests import graph

router = APIRouter(prefix="/config", dependencies=[Depends(require_staff)])


@router.get("", response_model=s.ConfigOut)
def get_config(db: Session = Depends(get_db)):
    return db.get(GlobalConfig, 1)


@router.put("", response_model=s.ConfigOut)
def put_config(body: s.ConfigIn, db: Session = Depends(get_db), admin: AppUser = Depends(require_admin)):
    cfg = db.get(GlobalConfig, 1)
    for k, v in body.model_dump().items():
        setattr(cfg, k, v)
    cfg.updated_by, cfg.updated_at = admin.id, now()
    db.commit()
    return cfg


@router.post("/test-mail")
def test_mail(db: Session = Depends(get_db), admin: AppUser = Depends(require_admin)):
    """Invia una mail di prova all'admin dal mittente configurato (verifica permessi Graph)."""
    cfg = db.get(GlobalConfig, 1)
    try:
        graph().request("POST", f"/users/{cfg.sender_email}/sendMail", json={
            "message": {"subject": "SRM – mail di prova",
                        "body": {"contentType": "Text", "content": "Configurazione Graph OK."},
                        "toRecipients": [{"emailAddress": {"address": admin.email}}]},
            "saveToSentItems": False})
    except Exception as e:
        raise HTTPException(502, f"Invio fallito: {e}")
    return {"ok": True, "to": admin.email}
