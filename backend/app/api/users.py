"""Gestione utenti e ruoli (solo ADMIN). L'agente commerciale è un utente con ruolo SALES."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import schemas as s
from app.api.auth import user_out
from app.config import settings
from app.db import get_db
from app.models import AppUser, UserRole
from app.passwords import generate_password, hash_password, validate_new_password
from app.security import require_admin

router = APIRouter(prefix="/users", dependencies=[Depends(require_admin)])


def _commit(db: Session):
    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        msg = str(e.orig)
        if "username" in msg:
            raise HTTPException(409, {"message": "Nome utente già in uso", "fields": {"username": "Già in uso"}})
        if "email" in msg and "chk_sales" not in msg:
            raise HTTPException(409, {"message": "Email già associata a un altro utente", "fields": {"email": "Già in uso"}})
        raise HTTPException(422, "Dati non validi")


def _get(db: Session, uid: int) -> AppUser:
    u = db.get(AppUser, uid)
    if not u:
        raise HTTPException(404, "Utente non trovato")
    return u


def _need_email(role: UserRole, email: str | None):
    if role == UserRole.SALES and not email:
        raise HTTPException(422, {"message": "Gli utenti Sales (agenti commerciali) richiedono un'email: viene messa in CC",
                                  "fields": {"email": "Obbligatoria per il ruolo Sales"}})


def _other_active_admins(db: Session, uid: int) -> int:
    return db.scalar(select(func.count()).select_from(AppUser).where(
        AppUser.role == UserRole.ADMIN, AppUser.is_active, AppUser.id != uid))


def _check_password(pw: str, username: str):
    try:
        validate_new_password(pw, username=username, forbidden=(settings.default_admin_password,))
    except ValueError as e:
        raise HTTPException(422, {"message": str(e), "fields": {"password": str(e), "new_password": str(e)}})


@router.get("", response_model=list[s.UserOut])
def list_users(db: Session = Depends(get_db)):
    return [user_out(u) for u in db.scalars(select(AppUser).order_by(AppUser.full_name, AppUser.id))]


@router.get("/generate-password")
def gen_password():
    """Password casuale da consegnare all'utente (andrà cambiata al primo accesso)."""
    return {"password": generate_password()}


@router.post("", response_model=s.UserOut, status_code=201)
def create_user(body: s.UserCreate, db: Session = Depends(get_db)):
    _need_email(body.role, body.email)
    _check_password(body.password, body.username)
    u = AppUser(username=body.username, full_name=body.full_name.strip(), email=body.email,
                role=body.role, is_active=body.is_active, password_hash=hash_password(body.password),
                must_change_password=True)
    db.add(u)
    _commit(db)
    return user_out(u)


@router.patch("/{uid}", response_model=s.UserOut)
def update_user(uid: int, body: s.UserUpdate, db: Session = Depends(get_db),
                me: AppUser = Depends(require_admin)):
    u = _get(db, uid)
    data = body.model_dump(exclude_unset=True)
    for k in ("role", "is_active", "full_name"):
        if k in data and data[k] is None:
            data.pop(k)
    if u.id == me.id and (data.get("role", u.role) != u.role or data.get("is_active", True) is False):
        raise HTTPException(409, "Non puoi cambiare il tuo ruolo né disattivare il tuo utente")
    new_role, new_active = data.get("role", u.role), data.get("is_active", u.is_active)
    if u.role == UserRole.ADMIN and u.is_active and (new_role != UserRole.ADMIN or not new_active) \
            and _other_active_admins(db, u.id) == 0:
        raise HTTPException(409, "Deve restare almeno un amministratore attivo")
    _need_email(new_role, data["email"] if "email" in data else u.email)
    for k, v in data.items():
        setattr(u, k, v)
    if "is_active" in data and not data["is_active"]:
        u.token_version += 1           # chiude subito le sessioni aperte
    _commit(db)
    return user_out(u)


@router.post("/{uid}/reset-password", response_model=s.UserOut)
def reset_password(uid: int, body: s.PasswordReset, db: Session = Depends(get_db)):
    """Imposta una password provvisoria: sblocca l'account e obbliga al cambio al prossimo accesso."""
    u = _get(db, uid)
    _check_password(body.new_password, u.username)
    u.password_hash = hash_password(body.new_password)
    u.must_change_password = True
    u.token_version += 1
    u.failed_logins, u.locked_until = 0, None
    db.commit()
    return user_out(u)
