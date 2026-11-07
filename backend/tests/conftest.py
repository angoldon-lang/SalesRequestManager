import os

os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://postgres@localhost:5432/srm_test")
assert os.environ["DATABASE_URL"].split("?")[0].endswith("_test"), \
    "I test cancellano lo schema: il DB deve terminare con _test"
os.environ["AUTH_DISABLED"] = "true"
os.environ["GRAPH_MODE"] = "dry-run"

import itertools  # noqa: E402
from pathlib import Path  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.db import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402

SCHEMA = Path(__file__).resolve().parents[1] / "db" / "schema.sql"


@pytest.fixture(scope="session", autouse=True)
def schema():
    with engine.begin() as c:
        c.exec_driver_sql("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
        c.exec_driver_sql(SCHEMA.read_text())
    yield


@pytest.fixture(autouse=True)
def clean():
    with engine.begin() as c:
        c.execute(text("TRUNCATE request_events, requests, inbound_emails, vendor_supplier_map, "
                       "suppliers, vendors, sales_agents, app_users, global_config RESTART IDENTITY CASCADE"))
        c.execute(text("INSERT INTO global_config (sender_email, inbound_mailbox, default_cc, "
                       "reminder_after_days, reminder_max_count) VALUES "
                       "('richieste@az.it','inbound@az.it','{admin@az.it,Rich@az.it}', 3, 2)"))
    yield


@pytest.fixture
def db():
    with SessionLocal() as s:
        yield s


class FakeGraph:
    """Simula il sottoinsieme di Graph usato da SRM."""

    def __init__(self):
        self.ids = itertools.count(1)
        self.sent: list[dict] = []          # messaggi inviati (payload)
        self.replies: list[dict] = []       # risposte vendor visibili in mailbox mittente
        self.inbox: list[dict] = []
        self.patched: list[tuple] = []
        self.moved: list[tuple] = []
        self.fail_send = False
        self._drafts: dict[str, dict] = {}

    def request(self, method, path, *, params=None, json=None, headers=None):
        if method == "POST" and path.endswith("/messages"):
            n = next(self.ids)
            d = {"id": f"m{n}", "conversationId": f"c{n}", "payload": json}
            self._drafts[d["id"]] = d
            return {"id": d["id"], "conversationId": d["conversationId"]}
        if method == "POST" and path.endswith("/send"):
            if self.fail_send:
                raise RuntimeError("Graph 500")
            mid = path.split("/")[-2]
            self.sent.append(self._drafts[mid])
            return None
        if method == "POST" and path.endswith("/createReplyAll"):
            n = next(self.ids)
            orig = path.split("/")[-2]
            self._drafts[f"r{n}"] = {"id": f"r{n}", "reply_to": orig, "payload": {}}
            return {"id": f"r{n}", "body": {"content": "<blockquote>originale</blockquote>"}}
        if method == "PATCH" and "/messages/r" in path:
            self._drafts[path.split("/")[-1]]["payload"] = json
            return None
        if method == "PATCH":
            self.patched.append((path, json))
            return None
        if method == "POST" and path.endswith("/move"):
            self.moved.append((path, json))
            return None
        if method == "GET" and "mailFolders/inbox/messages" in path:
            return {"value": [m for m in self.inbox if m["id"] not in {p.split('/')[-1] for p, _ in self.patched}]}
        if method == "GET" and path.endswith("/mailFolders"):
            return {"value": [{"id": "F1", "displayName": "SRM-Processed"}]}
        if method == "GET" and path.endswith("/messages"):
            conv = params["$filter"].split("'")[1]
            return {"value": [r for r in self.replies if r["conversationId"] == conv]}
        raise AssertionError(f"chiamata Graph inattesa: {method} {path}")

    def get_all(self, path, **kw):
        return self.request("GET", path, **kw)["value"]


@pytest.fixture
def graph():
    return FakeGraph()


@pytest.fixture
def client(graph):
    from app.api import requests as req_api
    req_api._graph = graph
    with TestClient(app) as c:
        yield c
    req_api._graph = None


def H(user="admin@az.it"):
    return {"X-Dev-User": user}


@pytest.fixture
def seed(client):
    h = H()
    v = client.post("/api/v1/vendors", json={"name": "Cisco"}, headers=h).json()
    sup = client.post("/api/v1/suppliers", json={"name": "Arrow"}, headers=h).json()
    ag = client.post("/api/v1/agents", json={"full_name": "Mario Rossi", "email": "Mario.Rossi@az.it"},
                     headers=h).json()
    m = client.put("/api/v1/vendor-supplier-map", headers=h, json={
        "vendor_id": v["id"], "supplier_id": sup["id"], "to_emails": ["Deals@Arrow.com"],
        "cc_emails": ["admin@az.it"], "is_preferred": True}).json()
    return {"vendor": v, "supplier": sup, "agent": ag, "map": m}
