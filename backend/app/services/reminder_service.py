"""Reminder automatici: invia un sollecito nello stesso thread dopo X giorni senza risposta."""
import logging
from datetime import datetime, timezone

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models import Request, RequestStatus
from app.services import mail_templates
from app.services.business_days import business_days_between
from app.services.request_service import add_event, get_config, now

log = logging.getLogger("srm.reminder")


def is_due(req: Request, cfg, ref: datetime) -> bool:
    last = req.last_reminder_at or req.sent_at
    if last is None:
        return False
    if cfg.reminder_business_days:
        return business_days_between(last.date(), ref.date()) >= cfg.reminder_after_days
    return (ref - last).days >= cfg.reminder_after_days


def send_reminder(db: Session, graph, cfg, req: Request, actor: str = "system:reminder") -> None:
    sender = cfg.sender_email
    draft = graph.request("POST", f"/users/{sender}/messages/{req.graph_message_id}/createReplyAll")
    prior = (draft.get("body") or {}).get("content", "")
    graph.request("PATCH", f"/users/{sender}/messages/{draft['id']}", json={
        "body": {"contentType": "HTML", "content": mail_templates.render_reminder(req) + prior}})
    graph.request("POST", f"/users/{sender}/messages/{draft['id']}/send")
    req.status = RequestStatus.REMINDED
    req.reminder_count += 1
    req.last_reminder_at = now()
    add_event(db, req, "REMINDER_SENT", actor, {"n": req.reminder_count})


def run_reminders(db: Session, graph, ref: datetime | None = None) -> dict:
    """Idempotente e sicuro con più istanze (FOR UPDATE SKIP LOCKED)."""
    ref = ref or datetime.now(timezone.utc)
    cfg = get_config(db)
    stats = {"sent": 0, "failed": 0, "skipped": 0}
    ids = db.execute(text("""
        SELECT id FROM requests
        WHERE status IN ('SENT','REMINDED')
          AND first_vendor_reply_at IS NULL
          AND graph_message_id IS NOT NULL
          AND reminder_count < :mx
          AND COALESCE(last_reminder_at, sent_at) <= :ref - make_interval(days => :days)
        ORDER BY COALESCE(last_reminder_at, sent_at)
        FOR UPDATE SKIP LOCKED
    """), {"mx": cfg.reminder_max_count, "ref": ref, "days": cfg.reminder_after_days}).scalars().all()

    for rid in ids:
        req = db.get(Request, rid)
        if not is_due(req, cfg, ref):          # il pre-filtro SQL usa i giorni di calendario
            stats["skipped"] += 1
            continue
        try:
            with db.begin_nested():
                send_reminder(db, graph, cfg, req)
            stats["sent"] += 1
        except Exception as e:                  # nessun cambio di stato: ritenta al prossimo giro
            log.exception("Reminder fallito per %s", req.code)
            add_event(db, req, "REMINDER_FAILED", "system:reminder", {"error": str(e)[:500]})
            stats["failed"] += 1
    db.commit()
    return stats


def to_escalate(db: Session) -> list[Request]:
    cfg = get_config(db)
    return list(db.scalars(select(Request).where(
        Request.status == RequestStatus.REMINDED,
        Request.first_vendor_reply_at.is_(None),
        Request.reminder_count >= cfg.reminder_max_count)))
