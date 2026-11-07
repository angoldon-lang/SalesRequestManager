"""Regole di business e transizioni di stato delle richieste."""
from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    CloseReason, GlobalConfig, Request, RequestEvent, RequestStatus, RequestType,
    SalesAgent, VendorSupplierMap,
)
from app.services import mail_templates

DR_FIELDS = ("end_customer_name", "estimated_deal_value", "expected_close_date")


def now() -> datetime:
    return datetime.now(timezone.utc)


def add_event(db: Session, req: Request, event_type: str, actor: str, payload: dict | None = None):
    db.add(RequestEvent(request_id=req.id, event_type=event_type, actor=actor, payload=payload))


def missing_dr_fields(req: Request) -> list[str]:
    if req.request_type != RequestType.DR:
        return []
    miss = []
    if not (req.end_customer_name or "").strip():
        miss.append("end_customer_name")
    if req.estimated_deal_value is None or Decimal(req.estimated_deal_value) <= 0:
        miss.append("estimated_deal_value")
    if req.expected_close_date is None:
        miss.append("expected_close_date")
    return miss


def get_config(db: Session) -> GlobalConfig:
    return db.get(GlobalConfig, 1)


def get_map(db: Session, vendor_id: int, supplier_id: int) -> VendorSupplierMap | None:
    return db.scalar(select(VendorSupplierMap).where(
        VendorSupplierMap.vendor_id == vendor_id, VendorSupplierMap.supplier_id == supplier_id))


def validate_for_send(db: Session, req: Request) -> VendorSupplierMap:
    errors: dict[str, str] = {}
    for f in missing_dr_fields(req):
        errors[f] = "Obbligatorio per le richieste DR"
    for f in ("vendor_id", "supplier_id", "sales_agent_id"):
        if getattr(req, f) is None:
            errors[f] = "Obbligatorio per l'invio"
    if not (req.subject or "").strip():
        errors["subject"] = "Obbligatorio"
    mapping = None
    if req.vendor_id and req.supplier_id:
        mapping = get_map(db, req.vendor_id, req.supplier_id)
        if mapping is None:
            errors["supplier_id"] = "Il supplier non è mappato su questo vendor"
        elif req.request_type == RequestType.DR and not mapping.supports_dr:
            errors["request_type"] = "Questo vendor/supplier non gestisce Deal Registration"
    if errors:
        raise HTTPException(422, {"message": "Validazione fallita", "fields": errors})
    return mapping


def _dedupe(addresses: list[str], exclude: set[str]) -> list[str]:
    seen, out = set(exclude), []
    for a in addresses:
        a = a.strip().lower()
        if a and a not in seen:
            seen.add(a)
            out.append(a)
    return out


def build_recipients(cfg: GlobalConfig, mapping: VendorSupplierMap, agent: SalesAgent):
    to = _dedupe(mapping.to_emails, set())
    cc = _dedupe([agent.email, *cfg.default_cc, *mapping.cc_emails], set(to))
    return to, cc


def send_request(db: Session, graph, req: Request, actor: str) -> Request:
    if req.status != RequestStatus.DRAFT:
        raise HTTPException(409, "Solo una bozza può essere inviata")
    mapping = validate_for_send(db, req)
    cfg = get_config(db)
    agent = db.get(SalesAgent, req.sales_agent_id)
    to, cc = build_recipients(cfg, mapping, agent)

    msg = {
        "subject": f"[{req.code}] {req.subject}",
        "body": {"contentType": "HTML", "content": mail_templates.render_request(req, agent.full_name)},
        "toRecipients": [{"emailAddress": {"address": a}} for a in to],
        "ccRecipients": [{"emailAddress": {"address": a}} for a in cc],
        "replyTo": [{"emailAddress": {"address": agent.email}}],
    }
    sender = cfg.sender_email
    draft = graph.request("POST", f"/users/{sender}/messages", json=msg)
    graph.request("POST", f"/users/{sender}/messages/{draft['id']}/send")

    req.graph_message_id = draft["id"]
    req.graph_conversation_id = draft["conversationId"]
    req.status = RequestStatus.SENT
    req.sent_at = now()
    req.needs_review = False
    add_event(db, req, "SENT", actor, {"to": to, "cc": cc})
    return req


def close_request(db: Session, req: Request, reason: CloseReason, actor: str,
                  vendor_dr_reference: str | None = None,
                  dr_approved_at: date | None = None, dr_expires_at: date | None = None) -> Request:
    if req.status == RequestStatus.DRAFT:
        raise HTTPException(409, "Una bozza non si chiude: eliminala")
    if req.status == RequestStatus.CLOSED:
        raise HTTPException(409, "Richiesta già chiusa")
    if vendor_dr_reference is not None:
        req.vendor_dr_reference = vendor_dr_reference
    if dr_approved_at is not None:
        req.dr_approved_at = dr_approved_at
    if dr_expires_at is not None:
        req.dr_expires_at = dr_expires_at
    if req.dr_approved_at and req.dr_expires_at and req.dr_expires_at < req.dr_approved_at:
        raise HTTPException(422, "La scadenza DR precede la data di approvazione")
    req.status = RequestStatus.CLOSED
    req.closed_at = now()
    req.close_reason = reason
    add_event(db, req, "CLOSED", actor, {"reason": reason.value})
    return req


def reopen_request(db: Session, req: Request, actor: str) -> Request:
    if req.status != RequestStatus.CLOSED:
        raise HTTPException(409, "Solo una richiesta chiusa può essere riaperta")
    req.status = RequestStatus.REMINDED if req.reminder_count else RequestStatus.SENT
    req.closed_at = None
    req.close_reason = None
    add_event(db, req, "REOPENED", actor)
    return req
