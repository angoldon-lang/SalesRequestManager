"""Gestione utenti a 3 livelli: ADMIN, BACKOFFICE (vede tutto), SALES (solo le sue)."""
import pytest

from tests.conftest import H

API = "/api/v1"
ADMIN, BACK, S1, S2 = H(), H("back1@az.it"), H("sales1@az.it"), H("sales2@az.it")


@pytest.fixture
def team(client, seed):
    """Due agenti collegati per email a due utenti SALES, più una richiesta per ciascuno."""
    ids = {}
    for n in (1, 2):
        ids[n] = client.post(f"{API}/agents", headers=ADMIN,
                             json={"full_name": f"Sales {n}", "email": f"sales{n}@az.it"}).json()["id"]
    for h in (ADMIN, BACK, S1, S2):                 # primo login: crea utenti e auto-collega gli agenti
        client.get(f"{API}/me", headers=h)

    def mk(h, **kw):
        body = {"request_type": "NUOVO", "subject": "Q", "vendor_id": seed["vendor"]["id"],
                "supplier_id": seed["supplier"]["id"], **kw}
        r = client.post(f"{API}/requests", json=body, headers=h)
        assert r.status_code == 201, r.text
        return r.json()

    r1, r2 = mk(S1), mk(S2)
    r3 = mk(ADMIN, sales_agent_id=ids[1])           # creata dall'admin per l'agente 1
    return {"agents": ids, "r1": r1, "r2": r2, "r3": r3, "mk": mk}


def test_roles_assigned_on_first_login(client):
    assert client.get(f"{API}/me", headers=ADMIN).json()["role"] == "ADMIN"
    assert client.get(f"{API}/me", headers=BACK).json()["role"] == "BACKOFFICE"
    assert client.get(f"{API}/me", headers=S1).json()["role"] == "SALES"


def test_sales_sees_only_own_requests(client, team):
    mine = client.get(f"{API}/requests", headers=S1).json()
    assert {r["id"] for r in mine["items"]} == {team["r1"]["id"], team["r3"]["id"]}   # propria + a suo nome
    assert mine["total"] == 2
    assert {r["id"] for r in client.get(f"{API}/requests", headers=S2).json()["items"]} == {team["r2"]["id"]}


@pytest.mark.parametrize("h", [ADMIN, BACK])
def test_admin_and_backoffice_see_everything(client, team, h):
    assert client.get(f"{API}/requests", headers=h).json()["total"] == 3


def test_sales_cannot_open_others_requests(client, team):
    rid = team["r2"]["id"]
    for call in (lambda: client.get(f"{API}/requests/{rid}", headers=S1),
                 lambda: client.get(f"{API}/requests/{rid}/events", headers=S1),
                 lambda: client.patch(f"{API}/requests/{rid}", json={"subject": "hack"}, headers=S1),
                 lambda: client.post(f"{API}/requests/{rid}/send", headers=S1),
                 lambda: client.delete(f"{API}/requests/{rid}", headers=S1)):
        assert call().status_code == 404            # 404, non 403: non si rivela l'esistenza
    assert client.get(f"{API}/requests/{rid}", headers=S2).status_code == 200


def test_sales_create_is_forced_to_own_agent(client, team, seed):
    other = team["agents"][2]
    r = team["mk"](S1, sales_agent_id=other)        # tenta di intestarla al collega
    assert r["sales_agent_id"] == team["agents"][1]
    res = client.patch(f"{API}/requests/{team['r1']['id']}", json={"sales_agent_id": other}, headers=S1)
    assert res.status_code == 403


def test_sales_can_send_and_remind_own_but_not_close(client, team):
    rid = team["r1"]["id"]
    assert client.post(f"{API}/requests/{rid}/send", headers=S1).status_code == 200
    assert client.post(f"{API}/requests/{rid}/remind", headers=S1).status_code == 200
    assert client.post(f"{API}/requests/{rid}/close", json={"reason": "WON"}, headers=S1).status_code == 403
    assert client.post(f"{API}/requests/{rid}/close", json={"reason": "WON"}, headers=BACK).status_code == 200
    assert client.post(f"{API}/requests/{rid}/reopen", headers=BACK).status_code == 403   # solo admin
    assert client.post(f"{API}/requests/{rid}/reopen", headers=ADMIN).status_code == 200


def test_sales_blocked_from_staff_areas(client, team):
    for path in ("/config", "/inbound", "/users"):
        assert client.get(f"{API}{path}", headers=S1).status_code == 403
    assert client.post(f"{API}/vendors", json={"name": "X"}, headers=S1).status_code == 403
    assert client.get(f"{API}/vendors", headers=S1).status_code == 200      # serve al form


def test_backoffice_reads_config_but_cannot_configure(client, team):
    assert client.get(f"{API}/config", headers=BACK).status_code == 200
    assert client.get(f"{API}/inbound", headers=BACK).status_code == 200
    cfg = client.get(f"{API}/config", headers=BACK).json()
    cfg.pop("updated_at")
    assert client.put(f"{API}/config", json=cfg, headers=BACK).status_code == 403
    assert client.post(f"{API}/vendors", json={"name": "X"}, headers=BACK).status_code == 403
    assert client.get(f"{API}/users", headers=BACK).status_code == 403
    assert client.get(f"{API}/users", headers=ADMIN).status_code == 200


def test_sales_sees_only_self_in_agents_and_no_vendor_emails(client, team):
    agents = client.get(f"{API}/agents", headers=S1).json()
    assert [a["email"] for a in agents] == ["sales1@az.it"]
    assert len(client.get(f"{API}/agents", headers=BACK).json()) == 3
    m = client.get(f"{API}/vendor-supplier-map", headers=S1).json()
    assert m and m[0]["to_emails"] == [] and m[0]["cc_emails"] == []        # mapping visibile, indirizzi no
    assert client.get(f"{API}/vendor-supplier-map", headers=BACK).json()[0]["to_emails"] == ["deals@arrow.com"]


def test_dashboard_is_scoped_for_sales(client, team):
    for rid in (team["r1"]["id"], team["r2"]["id"], team["r3"]["id"]):
        client.post(f"{API}/requests/{rid}/send", headers=ADMIN)
    assert client.get(f"{API}/dashboard/summary", headers=ADMIN).json()["totale"] == 3
    assert client.get(f"{API}/dashboard/summary", headers=BACK).json()["totale"] == 3
    assert client.get(f"{API}/dashboard/summary", headers=S1).json()["totale"] == 2
    assert client.get(f"{API}/dashboard/summary", headers=S2).json()["totale"] == 1
    assert sum(w["nuovo"] for w in client.get(f"{API}/dashboard/timeseries", headers=S2).json()) == 1
    assert client.get(f"{API}/dashboard/vendors", headers=S2).json()[0]["richieste"] == 1


def test_sales_without_linked_agent_sees_nothing_and_cannot_create(client, team, seed):
    h = H("sales9@az.it")                            # nessun agente con questa email
    assert client.get(f"{API}/requests", headers=h).json() == {"items": [], "total": 0}
    res = client.post(f"{API}/requests", headers=h, json={"request_type": "NUOVO", "subject": "Q"})
    assert res.status_code == 403
    # l'admin lo collega a mano a un agente e da quel momento vede le richieste di quell'agente
    uid = next(u["id"] for u in client.get(f"{API}/users", headers=ADMIN).json() if u["email"] == "sales9@az.it")
    free = client.post(f"{API}/agents", headers=ADMIN, json={"full_name": "Libero", "email": "libero@az.it"}).json()
    r = client.patch(f"{API}/users/{uid}", headers=ADMIN, json={"sales_agent_id": free["id"]})
    assert r.status_code == 200 and r.json()["sales_agent_id"] == free["id"]
    assert client.post(f"{API}/requests", headers=h, json={"request_type": "NUOVO", "subject": "Q"}).status_code == 201


def test_admin_changes_role_and_unlinks_agent(client, team):
    uid = next(u["id"] for u in client.get(f"{API}/users", headers=ADMIN).json() if u["email"] == "sales1@az.it")
    assert client.patch(f"{API}/users/{uid}", headers=ADMIN, json={"sales_agent_id": None}).json()["sales_agent_id"] is None
    assert client.patch(f"{API}/users/{uid}", headers=ADMIN, json={"role": "BACKOFFICE"}).json()["role"] == "BACKOFFICE"
    assert client.get(f"{API}/requests", headers=S1).json()["total"] == 3   # ora vede tutto
    assert client.patch(f"{API}/users/{uid}", headers=ADMIN, json={"is_active": False}).status_code == 200
    assert client.get(f"{API}/me", headers=S1).status_code == 403
