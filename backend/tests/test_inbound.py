from sqlalchemy import select

from app.models import InboundEmail, Request
from app.services.inbound_service import poll_inbound
from tests.conftest import H


class FakeParser:
    def __init__(self, result=None, error=None):
        self.result, self.error, self.calls = result, error, 0

    def parse(self, **kw):
        self.calls += 1
        if self.error:
            raise self.error
        return self.result


def mail(i="a1", sender="Mario.Rossi@az.it", body="ciao"):
    return {"id": i, "internetMessageId": f"<{i}@x>", "subject": "R: dr cisco", "receivedDateTime":
            "2026-11-05T08:00:00Z", "from": {"emailAddress": {"address": sender}},
            "body": {"contentType": "html", "content": f"<p>{body}</p><script>x()</script>"}}


GOOD = {"is_commercial_request": True, "request_type": "DR", "vendor_name": "cisco",
        "supplier_name": "Arow", "subject": "Cisco – ACME – switch", "body": "Registrare deal",
        "end_customer_name": "ACME", "estimated_deal_value": 45000, "currency": "EUR",
        "expected_close_date": "2026-12-31", "missing_fields": [], "confidence": 0.93}


def test_creates_draft_from_email(client, seed, graph, db):
    graph.inbox = [mail()]
    assert poll_inbound(db, graph, FakeParser(GOOD)) == 1
    r = db.scalars(select(Request)).one()
    assert r.status.value == "DRAFT" and r.source.value == "EMAIL_AI"
    assert r.vendor.name == "Cisco" and r.supplier.name == "Arrow"      # fuzzy match
    assert r.sales_agent.full_name == "Mario Rossi"                      # match per email mittente
    assert str(r.estimated_deal_value) == "45000.00" and r.needs_review is False
    assert db.scalars(select(InboundEmail)).one().status.value == "PARSED"
    assert graph.patched and graph.moved[0][1] == {"destinationId": "F1"}   # letto + spostato


def test_idempotent(client, seed, graph, db):
    graph.inbox = [mail()]
    p = FakeParser(GOOD)
    poll_inbound(db, graph, p)
    graph.patched.clear()
    poll_inbound(db, graph, p)
    assert p.calls == 1 and len(db.scalars(select(Request)).all()) == 1


def test_low_confidence_or_missing_goes_to_review(client, seed, graph, db):
    graph.inbox = [mail()]
    bad = {**GOOD, "confidence": 0.5, "end_customer_name": None, "missing_fields": ["end_customer_name"]}
    poll_inbound(db, graph, FakeParser(bad))
    r = db.scalars(select(Request)).one()
    assert r.needs_review and r.end_customer_name is None
    assert db.scalars(select(InboundEmail)).one().status.value == "NEEDS_REVIEW"
    # La bozza incompleta non è inviabile finché l'operatore non la completa
    res = client.post(f"/api/v1/requests/{r.id}/send", headers=H())
    assert res.status_code == 422


def test_unknown_sender_needs_review(client, seed, graph, db):
    graph.inbox = [mail(sender="sconosciuto@esterno.com")]
    poll_inbound(db, graph, FakeParser(GOOD))
    r = db.scalars(select(Request)).one()
    assert r.sales_agent_id is None and r.needs_review


def test_not_a_request_is_ignored(client, seed, graph, db):
    graph.inbox = [mail()]
    poll_inbound(db, graph, FakeParser({**GOOD, "is_commercial_request": False, "confidence": 0.1}))
    assert db.scalars(select(Request)).all() == []
    assert db.scalars(select(InboundEmail)).one().status.value == "IGNORED"


def test_llm_error_is_recorded(client, seed, graph, db):
    graph.inbox = [mail()]
    poll_inbound(db, graph, FakeParser(error=RuntimeError("API down")))
    row = db.scalars(select(InboundEmail)).one()
    assert row.status.value == "ERROR" and "API down" in row.error_message
    assert "x()" not in row.body_text                                   # html ripulito


def test_html_to_text_and_vendor_preferred_supplier(client, seed, graph, db):
    graph.inbox = [mail()]
    poll_inbound(db, graph, FakeParser({**GOOD, "supplier_name": None}))
    assert db.scalars(select(Request)).one().supplier.name == "Arrow"   # fallback preferito
