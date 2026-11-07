"""Autenticazione: validazione JWT Entra ID (v2) + provisioning utente al primo login."""
import jwt
from fastapi import Depends, Header, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models import AppUser, UserRole

bearer = HTTPBearer(auto_error=False)
_jwks: jwt.PyJWKClient | None = None


def _jwk_client() -> jwt.PyJWKClient:
    global _jwks
    if _jwks is None:
        _jwks = jwt.PyJWKClient(
            f"https://login.microsoftonline.com/{settings.az_tenant_id}/discovery/v2.0/keys")
    return _jwks


def _decode(token: str) -> dict:
    key = _jwk_client().get_signing_key_from_jwt(token).key
    return jwt.decode(
        token, key, algorithms=["RS256"],
        audience=settings.api_audience or settings.az_client_id,
        issuer=f"https://login.microsoftonline.com/{settings.az_tenant_id}/v2.0",
        options={"require": ["exp", "iss", "aud"]},
    )


def current_user(
    cred: HTTPAuthorizationCredentials | None = Depends(bearer),
    x_dev_user: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> AppUser:
    if settings.auth_disabled:
        email = (x_dev_user or "dev@local").lower()
        claims = {"preferred_username": email, "name": email.split("@")[0]}
        dev_role = UserRole.OPERATOR if x_dev_user and x_dev_user.startswith("op") else UserRole.ADMIN
    else:
        if cred is None:
            raise HTTPException(401, "Token mancante")
        try:
            claims = _decode(cred.credentials)
        except Exception:
            raise HTTPException(401, "Token non valido")
        dev_role = None

    email = (claims.get("preferred_username") or claims.get("email") or "").lower()
    if not email:
        raise HTTPException(401, "Token senza email")
    user = db.scalar(select(AppUser).where(AppUser.email == email))
    if user is None:
        is_admin = email in settings.admin_email_set or dev_role == UserRole.ADMIN
        # Primo login: la SPA lancia richieste parallele, quindi INSERT idempotente.
        db.execute(pg_insert(AppUser).values(
            email=email, entra_oid=claims.get("oid"), full_name=claims.get("name") or email,
            role=UserRole.ADMIN if is_admin else UserRole.OPERATOR).on_conflict_do_nothing())
        db.commit()
        user = db.scalar(select(AppUser).where(AppUser.email == email))
    if not user.is_active:
        raise HTTPException(403, "Utente disattivato")
    return user


def require_admin(user: AppUser = Depends(current_user)) -> AppUser:
    if user.role != UserRole.ADMIN:
        raise HTTPException(403, "Richiesto ruolo ADMIN")
    return user
