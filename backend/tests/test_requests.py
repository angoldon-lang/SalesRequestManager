import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from tests.conftest import H

API = "/api/v1"


def new_req(client, seed, **kw):
    body = {"request_type": "NUOVO", "subject": "Quotazione switch", "body": "Serve quotazione",
            "vendor_id": seed["vendor"]["id"], "supplier_id": seed["supplier"]["id"],
            "sales_agent_id": seed["agent"]["id"], **kw}
    r = client.post(f"{API}/requests", json=body, headers=H())
    assert r.status_code == 201, r.text
    return r.json()


def test_code_and_draft_defaults(client, seed):
    r = new_req(client, seed)
    assert r["code"].startswith("SRM-") and r["status"] == "DRAFT"


def test_dr_draft_can_be_incomplete_but_send_enforces_fields(client, seed):
    r = new_req(client, seed, request_type="DR")
    res = client.post(f"{API}/requests/{r['id']}/send", headers=H())
    assert res.status_code == 422
    assert set(res.json()["detail"]["fields"]) == {
        "end_customer_name", "estimated_deal_value", "expected_close_date"}


def test_dr_send_ok_with_mandatory_fields(client, seed, graph):
    r = new_req(client, seed, request_type="DR", end_customer_name="ACME Spa",
                estimated_deal_value="45000.00", expected_close_date="2026-12-31")
    res = client.post(f"{API}/requests/{r['id']}/send", headers=H())
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "SENT"
    html = graph.sent[0]["payload"]["body"]["content"]
    assert "ACME Spa" in html and "45,000.00" in html and "31/12/2026" in html


def test_recipients_sender_to_cc_dedup(client, seed, graph):
    r = new_req(client, seed)
    client.post(f"{API}/requests/{r['id']}/send", headers=H())
    p = graph.sent[0]["payload"]
    to = [x["emailAddress"]["address"] for x in p["toRecipients"]]
    cc = [x["emailAddress"]["address"] for x in p["ccRecipients"]]
    assert to == ["deals@arrow.com"]
    # agente + default CC + CC mapping, senza duplicati (admin@az.it compare 3 volte), lowercase
    assert cc == ["mario.rossi@az.it", "admin@az.it", "rich@az.it"]
    assert p["subject"].startswith(f"[{r['code']}]")


def test_send_requires_mapping(client, seed):
    other = client.post(f"{API}/suppliers", json={"name": "Ingram"}, headers=H()).json()
    r = new_req(client, seed, supplier_id=other["id"])
    res = client.post(f"{API}/requests/{r['id']}/send", headers=H())
    assert res.status_code == 422 and "supplier_id" in res.json()["detail"]["fields"]


def test_cannot_send_twice_or_edit_locked_fields(client, seed):
    r = new_req(client, seed)
    assert client.post(f"{API}/requests/{r['id']}/send", headers=H()).status_code == 200
    assert client.post(f"{API}/requests/{r['id']}/send", headers=H()).status_code == 409
    res = client.patch(f"{API}/requests/{r['id']}", json={"subject": "altro"}, headers=H())
    assert res.status_code == 409


def test_sent_dr_cannot_lose_mandatory_fields(client, seed):
    r = new_req(client, seed, request_type="DR", end_customer_name="ACME",
                estimated_deal_value="10", expected_close_date="2026-12-31")
    client.post(f"{API}/requests/{r['id']}/send", headers=H())
    res = client.patch(f"{API}/requests/{r['id']}", json={"end_customer_name": "  "}, headers=H())
    assert res.status_code == 422


def test_db_constraint_blocks_incomplete_dr_outside_draft(db):
    with pytest.raises(IntegrityError):
        db.execute(text("""INSERT INTO vendors(name) VALUES ('x');
            INSERT INTO suppliers(name) VALUES ('y');
            INSERT INTO requests(request_type,status,subject,vendor_id,supplier_id,sent_at)
            VALUES ('DR','SENT','s',1,1,now())"""))
        db.commit()


def test_close_reopen_and_rbac(client, seed):
    r = new_req(client, seed, request_type="DR", end_customer_name="ACME",
                estimated_deal_value="10", expected_close_date="2026-12-31")
    rid = r["id"]
    assert client.post(f"{API}/requests/{rid}/close", json={"reason": "APPROVED"},
                       headers=H()).status_code == 409           # bozza non chiudibile
    client.post(f"{API}/requests/{rid}/send", headers=H())
    res = client.post(f"{API}/requests/{rid}/close", headers=H("op1@az.it"), json={
        "reason": "APPROVED", "vendor_dr_reference": "DR-99",
        "dr_approved_at": "2026-11-10", "dr_expires_at": "2027-05-10"})
    assert res.status_code == 200 and res.json()["status"] == "CLOSED"
    assert res.json()["vendor_dr_reference"] == "DR-99"
    # l'operatore non può riaprire, l'admin sì
    assert client.post(f"{API}/requests/{rid}/reopen", headers=H("op1@az.it")).status_code == 403
    assert client.post(f"{API}/requests/{rid}/reopen", headers=H()).json()["status"] == "SENT"


def test_operator_cannot_write_config(client):
    client.get(f"{API}/me", headers=H("op1@az.it"))
    assert client.get(f"{API}/me", headers=H("op1@az.it")).json()["role"] == "OPERATOR"
    cfg = client.get(f"{API}/config", headers=H("op1@az.it")).json()
    cfg.pop("updated_at")
    assert client.put(f"{API}/config", json=cfg, headers=H("op1@az.it")).status_code == 403
    cfg["reminder_after_days"] = 5
    assert client.put(f"{API}/config", json=cfg, headers=H()).json()["reminder_after_days"] == 5


def test_list_filters_and_dashboard(client, seed):
    a = new_req(client, seed)
    b = new_req(client, seed, request_type="DR", end_customer_name="ACME",
                estimated_deal_value="10", expected_close_date="2026-12-31")
    for r in (a, b):
        client.post(f"{API}/requests/{r['id']}/send", headers=H())
    new_req(client, seed)  # resta bozza
    lst = client.get(f"{API}/requests", params={"type": "DR"}, headers=H()).json()
    assert lst["total"] == 1 and lst["items"][0]["vendor_name"] == "Cisco"
    assert client.get(f"{API}/requests", params={"q": "ACME"}, headers=H()).json()["total"] == 1
    client.post(f"{API}/requests/{a['id']}/close", json={"reason": "WON"}, headers=H())
    s = client.get(f"{API}/dashboard/summary", headers=H()).json()
    assert (s["totale"], s["nuovo"], s["dr"], s["aperte"], s["chiuse"], s["bozze"]) == (2, 1, 1, 1, 1, 1)
    assert s["pct_dr"] == 50.0 and s["pct_chiuse"] == 50.0
    assert client.get(f"{API}/dashboard/timeseries", headers=H()).json()[0]["nuovo"] == 1
    assert client.get(f"{API}/dashboard/vendors", headers=H()).json()[0]["name"] == "Cisco"


def test_only_one_preferred_supplier(client, seed):
    s2 = client.post(f"{API}/suppliers", json={"name": "Ingram"}, headers=H()).json()
    client.put(f"{API}/vendor-supplier-map", headers=H(), json={
        "vendor_id": seed["vendor"]["id"], "supplier_id": s2["id"],
        "to_emails": ["x@ingram.com"], "is_preferred": True})
    maps = client.get(f"{API}/vendor-supplier-map", headers=H()).json()
    assert sum(m["is_preferred"] for m in maps) == 1
