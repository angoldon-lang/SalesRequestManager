"""Rileva le risposte dei vendor nella mailbox mittente (per metriche e per fermare i reminder)."""
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Request, RequestStatus
from app.services.request_service import add_event, get_config


def track_replies(db: Session, graph) -> int:
    sender = str(get_config(db).sender_email).lower()
    reqs = db.scalars(select(Request).where(
        Request.status.in_([RequestStatus.SENT, RequestStatus.REMINDED]),
        Request.first_vendor_reply_at.is_(None),
        Request.graph_conversation_id.is_not(None))).all()
    found = 0
    for req in reqs:
        # Filtro solo su conversationId (combinare più filtri dà "InefficientFilter"), il resto lato client.
        msgs = graph.request("GET", f"/users/{sender}/messages", params={
            "$filter": f"conversationId eq '{req.graph_conversation_id}'",
            "$select": "id,receivedDateTime,from", "$top": 50})["value"]
        replies = sorted(
            (m for m in msgs
             if m.get("from", {}).get("emailAddress", {}).get("address", "").lower() != sender),
            key=lambda m: m["receivedDateTime"])
        if replies:
            req.first_vendor_reply_at = datetime.fromisoformat(
                replies[0]["receivedDateTime"].replace("Z", "+00:00"))
            add_event(db, req, "VENDOR_REPLY", "system:reply_tracker",
                      {"from": replies[0]["from"]["emailAddress"]["address"]})
            found += 1
    db.commit()
    return found
