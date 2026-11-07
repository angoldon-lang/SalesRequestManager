from datetime import datetime, timezone

from sqlalchemy import select, text

from app.models import Request, RequestEvent
from app.services.reminder_service import run_reminders, to_escalate
from app.services.reply_tracker import track_replies
from tests.conftest import H

API = "/api/v1"
UTC = timezone.utc


def sent_request(client, seed, sent_at: str):
    r = client.post(f"{API}/requests", headers=H(), json={
        "request_type": "NUOVO", "subject": "Q", "vendor_id": seed["vendor"]["id"],
        "supplier_id": seed["supplier"]["id"], "sales_agent_id": seed["agent"]["id"]}).json()
    client.post(f"{API}/requests/{r['id']}/send", headers=H())
    with __import__("app.db", fromlist=["engine"]).engine.begin() as c:
        c.execute(text("UPDATE requests SET sent_at=:s WHERE id=:i"), {"s": sent_at, "i": r["id"]})
    return r["id"]


def ref(day):  # lunedì 2026-11-09 è feriale
    return datetime(2026, 11, *day, 10, 0, tzinfo=UTC)


def test_reminder_after_x_business_days(client, seed, graph, db):
    rid = sent_request(client, seed, "2026-11-02T09:00:00+00:00")        # lunedì
    assert run_reminders(db, graph, ref((4,)))["sent"] == 0              # 2 gg lavorativi < 3
    assert run_reminders(db, graph, ref((5,)))["sent"] == 1              # 3 gg lavorativi
    r = db.get(Request, rid)
    assert r.status.value == "REMINDED" and r.reminder_count == 1
    reply = [d for d in graph._drafts.values() if d.get("reply_to")][0]
    assert reply["reply_to"] == r.graph_message_id                       # stesso thread
    assert "originale" in reply["payload"]["body"]["content"]            # quoting mantenuto


def test_weekend_does_not_count(client, seed, graph, db):
    sent_request(client, seed, "2026-11-06T09:00:00+00:00")              # venerdì
    # lunedì 9: 3 giorni di calendario ma solo 1 lavorativo -> niente reminder
    assert run_reminders(db, graph, ref((9,)))["sent"] == 0
    assert run_reminders(db, graph, ref((11,)))["sent"] == 1             # mercoledì: 3 lavorativi


def test_max_reminders_then_escalation(client, seed, graph, db):
    rid = sent_request(client, seed, "2026-10-01T09:00:00+00:00")
    assert run_reminders(db, graph, ref((9,)))["sent"] == 1
    db.execute(text("UPDATE requests SET last_reminder_at='2026-10-05' WHERE id=:i"), {"i": rid})
    db.commit()
    assert run_reminders(db, graph, ref((9,)))["sent"] == 1              # secondo (max=2)
    db.execute(text("UPDATE requests SET last_reminder_at='2026-10-10' WHERE id=:i"), {"i": rid})
    db.commit()
    assert run_reminders(db, graph, ref((9,)))["sent"] == 0              # limite raggiunto
    assert [r.id for r in to_escalate(db)] == [rid]


def test_no_reminder_after_vendor_reply(client, seed, graph, db):
    rid = sent_request(client, seed, "2026-11-02T09:00:00+00:00")
    conv = db.get(Request, rid).graph_conversation_id
    graph.replies = [
        {"conversationId": conv, "receivedDateTime": "2026-11-03T08:00:00Z",
         "from": {"emailAddress": {"address": "deals@arrow.com"}}},
        {"conversationId": conv, "receivedDateTime": "2026-11-02T09:00:05Z",   # nostra stessa mail
         "from": {"emailAddress": {"address": "richieste@az.it"}}},
    ]
    assert track_replies(db, graph) == 1
    r = db.get(Request, rid)
    assert r.first_vendor_reply_at == datetime(2026, 11, 3, 8, 0, tzinfo=UTC)
    assert run_reminders(db, graph, ref((10,)))["sent"] == 0
    assert db.scalars(select(RequestEvent.event_type).where(RequestEvent.request_id == rid)
                      ).all().count("VENDOR_REPLY") == 1


def test_failed_reminder_keeps_state(client, seed, graph, db):
    rid = sent_request(client, seed, "2026-11-02T09:00:00+00:00")
    graph.fail_send = True
    assert run_reminders(db, graph, ref((9,)))["failed"] == 1
    r = db.get(Request, rid)
    assert r.status.value == "SENT" and r.reminder_count == 0
    graph.fail_send = False
    assert run_reminders(db, graph, ref((9,)))["sent"] == 1               # ritenta al giro dopo


def test_manual_remind_endpoint(client, seed):
    rid = sent_request(client, seed, "2026-11-08T09:00:00+00:00")
    res = client.post(f"{API}/requests/{rid}/remind", headers=H())
    assert res.status_code == 200 and res.json()["reminder_count"] == 1
