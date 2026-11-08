"""Autorizzazione a 3 livelli.

- ADMIN      (Admin / Direzione Sales): vede tutto, configura, gestisce utenti e anagrafiche.
- BACKOFFICE: vede tutto, opera su tutte le richieste (crea, invia, sollecita, chiude); non configura.
- SALES:      vede solo le proprie richieste (agente collegato oppure create da lui).
"""
from fastapi import Depends, HTTPException
from sqlalchemy import or_

from app.models import AppUser, Request, UserRole
from app.security import current_user

STAFF = (UserRole.ADMIN, UserRole.BACKOFFICE)


def is_staff(user: AppUser) -> bool:
    return user.role in STAFF


def require_staff(user: AppUser = Depends(current_user)) -> AppUser:
    if not is_staff(user):
        raise HTTPException(403, "Funzione riservata a Backoffice e Admin")
    return user


def request_scope(user: AppUser):
    """Condizione SQLAlchemy da applicare alle query su Request (None = nessuna restrizione)."""
    if is_staff(user):
        return None
    conds = [Request.created_by == user.id]
    if user.sales_agent_id:
        conds.append(Request.sales_agent_id == user.sales_agent_id)
    return or_(*conds)


def can_see(user: AppUser, r: Request) -> bool:
    return is_staff(user) or r.created_by == user.id or (
        user.sales_agent_id is not None and r.sales_agent_id == user.sales_agent_id)


def scope_sql(user: AppUser, alias: str = "") -> tuple[str, dict]:
    """Stesso filtro per le query SQL testuali della dashboard."""
    if is_staff(user):
        return "", {}
    p = f"{alias}." if alias else ""
    return (f" AND ({p}created_by = :scope_uid OR {p}sales_agent_id = :scope_aid)",
            {"scope_uid": user.id, "scope_aid": user.sales_agent_id})
