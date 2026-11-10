"""Autenticazione: locale (utente/password + JWT firmato), Microsoft Entra ID, o sviluppo/test."""
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, Header, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models import AppUser, GlobalConfig, UserRole

bearer = HTTPBearer(auto_error=False)
ALGO = "HS256"
_key_cache: str | None = None


def auth_mode() -> str:
    return "dev" if settings.auth_disabled else settings.auth_mode


# ---------------------------------------------------------------- token locali
def signing_key(db: Session) -> str:
    """SECRET_KEY da ambiente; altrimenti una chiave casuale generata una volta e salvata nel DB."""
    global _key_cache
    if settings.secret_key:
        return settings.secret_key
    if _key_cache:
        return _key_cache
    cfg = db.get(GlobalConfig, 1)
    if cfg.jwt_secret is None:
        cfg.jwt_secret = secrets.token_urlsafe(48)
        db.commit()
    _key_cache = cfg.jwt_secret
    return _key_cache


def create_token(db: Session, user: AppUser) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {"sub": str(user.id), "tv": user.token_version, "iat": now,
         "exp": now + timedelta(minutes=settings.token_ttl_minutes)},
        signing_key(db), algorithm=ALGO)


def _user_from_local_token(db: Session, token: str) -> AppUser:
    try:
        claims = jwt.decode(token, signing_key(db), algorithms=[ALGO], options={"require": ["exp", "sub"]})
        user = db.get(AppUser, int(claims["sub"]))
    except Exception:
        raise HTTPException(401, "Sessione non valida o scaduta")
    if not user or not user.is_active or claims.get("tv") != user.token_version:
        raise HTTPException(401, "Sessione non valida o scaduta")
    return user


# ---------------------------------------------------------------- Entra ID
_jwks: jwt.PyJWKClient | None = None


def _decode_entra(token: str) -> dict:
    global _jwks
    if _jwks is None:
        _jwks = jwt.PyJWKClient(f"https://login.microsoftonline.com/{settings.az_tenant_id}/discovery/v2.0/keys")
    key = _jwks.get_signing_key_from_jwt(token).key
    return jwt.decode(
        token, key, algorithms=["RS256"], audience=settings.api_audience or settings.az_client_id,
        issuer=f"https://login.microsoftonline.com/{settings.az_tenant_id}/v2.0",
        options={"require": ["exp", "iss", "aud"]})


def _provision(db: Session, email: str, claims: dict, role: UserRole) -> AppUser:
    """Primo accesso: la SPA lancia richieste parallele, quindi INSERT idempotente."""
    db.execute(pg_insert(AppUser).values(
        username=email, email=email, entra_oid=claims.get("oid"),
        full_name=claims.get("name") or email, role=role).on_conflict_do_nothing())
    db.commit()
    return db.scalar(select(AppUser).where(AppUser.email == email))


def _user_from_entra_or_dev(db: Session, cred, x_dev_user) -> AppUser:
    if settings.auth_disabled:
        email = (x_dev_user or "dev@local").lower()
        claims = {"name": email.split("@")[0]}
        h = email
        role = (UserRole.BACKOFFICE if h.startswith("back") else
                UserRole.SALES if h.startswith("sales") else UserRole.ADMIN)
    else:
        if cred is None:
            raise HTTPException(401, "Token mancante")
        try:
            claims = _decode_entra(cred.credentials)
        except Exception:
            raise HTTPException(401, "Token non valido")
        email = (claims.get("preferred_username") or claims.get("email") or "").lower()
        if not email:
            raise HTTPException(401, "Token senza email")
        role = UserRole.ADMIN if email in settings.admin_email_set else UserRole(settings.default_role.upper())
    user = db.scalar(select(AppUser).where(AppUser.email == email))
    return user or _provision(db, email, claims, role)


# ---------------------------------------------------------------- dipendenze FastAPI
def current_user_any(
    cred: HTTPAuthorizationCredentials | None = Depends(bearer),
    x_dev_user: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> AppUser:
    """Utente autenticato, anche se deve ancora cambiare la password (solo /me e cambio password)."""
    if auth_mode() == "local":
        if cred is None:
            raise HTTPException(401, "Accesso richiesto")
        user = _user_from_local_token(db, cred.credentials)
    else:
        user = _user_from_entra_or_dev(db, cred, x_dev_user)
    if not user.is_active:
        raise HTTPException(403, "Utente disattivato")
    return user


def current_user(user: AppUser = Depends(current_user_any)) -> AppUser:
    if user.must_change_password and auth_mode() == "local":
        raise HTTPException(403, {"code": "PASSWORD_CHANGE_REQUIRED", "message": "Devi cambiare la password"})
    return user


def require_admin(user: AppUser = Depends(current_user)) -> AppUser:
    if user.role != UserRole.ADMIN:
        raise HTTPException(403, "Richiesto ruolo ADMIN")
    return user
