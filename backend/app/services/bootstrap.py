"""Primo avvio: crea l'amministratore predefinito se non esiste nessun admin in grado di accedere."""
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import AppUser, UserRole
from app.passwords import hash_password

log = logging.getLogger("srm.bootstrap")


def ensure_default_admin(db: Session) -> bool:
    """Ritorna True se ha creato/ripristinato l'admin predefinito."""
    has_admin = db.scalar(select(AppUser.id).where(
        AppUser.role == UserRole.ADMIN, AppUser.is_active, AppUser.password_hash.is_not(None)).limit(1))
    if has_admin:
        return False
    username = settings.default_admin_username
    user = db.scalar(select(AppUser).where(AppUser.username == username))
    if user is None:
        user = AppUser(username=username, full_name="Amministratore")
        db.add(user)
    user.role, user.is_active = UserRole.ADMIN, True
    user.password_hash = hash_password(settings.default_admin_password)
    user.must_change_password = True
    user.token_version = (user.token_version or 0) + 1
    user.failed_logins, user.locked_until = 0, None
    db.commit()
    log.warning("Creato l'utente '%s' con la password predefinita: va cambiata al primo accesso.", username)
    return True
