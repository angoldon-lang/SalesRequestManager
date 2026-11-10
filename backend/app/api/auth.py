"""Login locale, cambio password, modalità di autenticazione."""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import schemas as s
from app.config import settings
from app.db import get_db
from app.models import AppUser
from app.passwords import DUMMY_HASH, hash_password, validate_new_password, verify_password
from app.security import auth_mode, create_token, current_user_any

router = APIRouter(prefix="/auth")
MAX_FAILED = 5
LOCK_MINUTES = 15


def user_out(u: AppUser) -> s.UserOut:
    o = s.UserOut.model_validate(u)
    o.has_password = u.password_hash is not None
    return o


def _token_out(db: Session, u: AppUser) -> s.TokenOut:
    return s.TokenOut(access_token=create_token(db, u), must_change_password=u.must_change_password,
                      user=user_out(u))


@router.get("/config")
def config():
    """Pubblico: la UI decide quale schermata di accesso mostrare."""
    return {"mode": auth_mode()}


@router.post("/login", response_model=s.TokenOut)
def login(body: s.LoginIn, db: Session = Depends(get_db)):
    if auth_mode() != "local":
        raise HTTPException(404, "Accesso con password non attivo")
    now = datetime.now(timezone.utc)
    user = db.scalar(select(AppUser).where(AppUser.username == body.username.strip()))
    if user and user.locked_until and user.locked_until > now:
        mins = int((user.locked_until - now).total_seconds() // 60) + 1
        raise HTTPException(429, f"Troppi tentativi falliti. Riprova tra {mins} minuti")
    # si verifica sempre un hash, anche per utenti inesistenti: tempi di risposta uniformi
    ok = verify_password(body.password, user.password_hash if user and user.password_hash else DUMMY_HASH)
    if not (user and user.password_hash and user.is_active and ok):
        if user:
            user.failed_logins += 1
            if user.failed_logins >= MAX_FAILED:
                user.locked_until, user.failed_logins = now + timedelta(minutes=LOCK_MINUTES), 0
            db.commit()
        raise HTTPException(401, "Utente o password non corretti")
    user.failed_logins, user.locked_until, user.last_login_at = 0, None, now
    db.commit()
    return _token_out(db, user)


@router.post("/change-password", response_model=s.TokenOut)
def change_password(body: s.ChangePasswordIn, db: Session = Depends(get_db),
                    user: AppUser = Depends(current_user_any)):
    if auth_mode() != "local":
        raise HTTPException(404, "Accesso con password non attivo")
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(422, {"message": "Password attuale errata",
                                  "fields": {"current_password": "Password attuale errata"}})
    try:
        validate_new_password(body.new_password, username=user.username,
                              forbidden=(body.current_password, settings.default_admin_password))
    except ValueError as e:
        raise HTTPException(422, {"message": str(e), "fields": {"new_password": str(e)}})
    user.password_hash = hash_password(body.new_password)
    user.must_change_password = False
    user.token_version += 1            # invalida le altre sessioni aperte
    db.commit()
    return _token_out(db, user)
