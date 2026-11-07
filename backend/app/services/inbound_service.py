"""Worker inbound: legge la mailbox dedicata, estrae i dati con l'LLM e crea bozze."""
import logging
from datetime import date, datetime, timezone
from decimal import Decimal

from bs4 import BeautifulSoup
from rapidfuzz import fuzz, process, utils
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    InboundEmail, InboundStatus, Request, RequestSource, RequestStatus, RequestType,
    SalesAgent, Supplier, Vendor, VendorSupplierMap,
)
from app.services import llm_parser
from app.services.request_service import add_event, get_config, now

log = logging.getLogger("srm.inbound")
CONFIDENCE_THRESHOLD = 0.70
FUZZY_THRESHOLD = 85


def fuzzy_pick(name: str | None, rows):
    if not name or not rows:
        return None
    best = process.extractOne(name, {r.id: r.name for r in rows}, scorer=fuzz.WRatio, processor=utils.default_process,
                              score_cutoff=FUZZY_THRESHOLD)
    return next((r for r in rows if r.id == best[2]), None) if best else None


def html_to_text(content: str, content_type: str) -> str:
    if content_type.lower() == "html":
        return BeautifulSoup(content, "html.parser").get_text("\n", strip=True)
    return content


def _parse_date(s) -> date | None:
    try:
        return date.fromisoformat(s) if s else None
    except ValueError:
        return None


def create_draft(db: Session, row: InboundEmail, parsed: dict) -> Request | None:
    """Crea la bozza dal risultato LLM. Ritorna None se l'email non è una richiesta."""
    p = llm_parser.normalize(parsed)
    row.llm_raw_output = parsed
    if not p.get("is_commercial_request", True):
        row.status = InboundStatus.IGNORED
        return None

    vendor = fuzzy_pick(p.get("vendor_name"), db.scalars(select(Vendor).where(Vendor.is_active)).all())
    supplier = fuzzy_pick(p.get("supplier_name"),
                          db.scalars(select(Supplier).where(Supplier.is_active)).all())
    if vendor and not supplier:       # fallback: supplier preferito del vendor
        pref = db.scalar(select(VendorSupplierMap).where(
            VendorSupplierMap.vendor_id == vendor.id, VendorSupplierMap.is_preferred))
        supplier = db.get(Supplier, pref.supplier_id) if pref else None
    agent = db.scalar(select(SalesAgent).where(
        SalesAgent.email == str(row.from_email).lower(), SalesAgent.is_active))

    needs_review = (p["confidence"] < CONFIDENCE_THRESHOLD or bool(p["missing_fields"])
                    or vendor is None or supplier is None or agent is None)
    value = p.get("estimated_deal_value")
    req = Request(
        request_type=RequestType(p["request_type"]), status=RequestStatus.DRAFT,
        source=RequestSource.EMAIL_AI, inbound_email_id=row.id,
        vendor_id=vendor.id if vendor else None, supplier_id=supplier.id if supplier else None,
        sales_agent_id=agent.id if agent else None,
        subject=p["subject"], body=p.get("body"), product_description=p.get("product_description"),
        quantity=p.get("quantity") if (p.get("quantity") or 0) > 0 else None,
        end_customer_name=p.get("end_customer_name"),
        estimated_deal_value=Decimal(str(value)) if value else None,
        currency=p["currency"], expected_close_date=_parse_date(p.get("expected_close_date")),
        ai_confidence=Decimal(str(round(p["confidence"], 2))), needs_review=needs_review,
    )
    db.add(req)
    db.flush()
    add_event(db, req, "CREATED", "system:inbound",
              {"inbound_email_id": row.id, "notes": p.get("notes"), "missing": p["missing_fields"]})
    row.status = InboundStatus.NEEDS_REVIEW if needs_review else InboundStatus.PARSED
    return req


def process_row(db: Session, row: InboundEmail, parser, model: str) -> None:
    try:
        parsed = parser.parse(
            subject=row.subject or "", body=row.body_text or "", from_email=str(row.from_email),
            from_name=str(row.from_email).split("@")[0],
            received_at=row.received_at.isoformat(), model=model)
        create_draft(db, row, parsed)
    except Exception as e:
        log.exception("Parsing fallito per inbound %s", row.id)
        row.status, row.error_message = InboundStatus.ERROR, str(e)[:1000]
    row.processed_at = now()


def _folder_id(graph, mailbox: str, name: str) -> str | None:
    folders = graph.get_all(f"/users/{mailbox}/mailFolders", params={"$top": 100})
    return next((f["id"] for f in folders if f["displayName"].lower() == name.lower()), None)


def poll_inbound(db: Session, graph, parser) -> int:
    cfg = get_config(db)
    mbox = str(cfg.inbound_mailbox)
    msgs = graph.request("GET", f"/users/{mbox}/mailFolders/inbox/messages", params={
        "$filter": "isRead eq false", "$orderby": "receivedDateTime asc", "$top": 20,
        "$select": "id,internetMessageId,subject,from,body,receivedDateTime"})["value"]
    folder = _folder_id(graph, mbox, cfg.inbound_processed_folder) if msgs else None
    done = 0
    for m in msgs:
        if db.scalar(select(InboundEmail.id).where(InboundEmail.graph_message_id == m["id"])):
            continue
        row = InboundEmail(
            graph_message_id=m["id"], internet_msg_id=m.get("internetMessageId"),
            from_email=m["from"]["emailAddress"]["address"].lower(), subject=m.get("subject"),
            body_text=html_to_text(m["body"]["content"], m["body"].get("contentType", "text")),
            received_at=datetime.fromisoformat(m["receivedDateTime"].replace("Z", "+00:00")),
        )
        db.add(row)
        db.flush()
        process_row(db, row, parser, cfg.llm_model)
        db.commit()               # prima il DB: se Graph fallisce, l'idempotenza evita doppioni
        try:
            graph.request("PATCH", f"/users/{mbox}/messages/{m['id']}", json={"isRead": True})
            if folder:
                graph.request("POST", f"/users/{mbox}/messages/{m['id']}/move",
                              json={"destinationId": folder})
        except Exception:
            log.exception("Impossibile marcare/spostare il messaggio %s", m["id"])
        done += 1
    return done
