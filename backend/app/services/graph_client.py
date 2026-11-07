"""Client Microsoft Graph (client credentials) + modalità dry-run per sviluppo."""
import itertools
import logging
import time
import uuid
from typing import Any

import httpx

from app.config import settings

log = logging.getLogger("srm.graph")
BASE = "https://graph.microsoft.com/v1.0"


class Graph:
    """Wrapper minimale: ritenta su 429/503 rispettando Retry-After.

    Prefer IdType=ImmutableId: gli id dei messaggi non cambiano quando Exchange
    sposta la bozza in "Posta inviata" (indispensabile per reminder e tracking).
    """

    def __init__(self) -> None:
        import msal
        self.app = msal.ConfidentialClientApplication(
            settings.az_client_id,
            authority=f"https://login.microsoftonline.com/{settings.az_tenant_id}",
            client_credential=settings.az_client_secret,
        )

    def _headers(self, extra: dict | None = None) -> dict:
        res = self.app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
        if "access_token" not in res:
            raise RuntimeError(f"Token Graph non ottenuto: {res.get('error_description')}")
        h = {"Authorization": f"Bearer {res['access_token']}", "Prefer": 'IdType="ImmutableId"'}
        if extra:
            h.update(extra)
        return h

    def request(self, method: str, path: str, *, params: dict | None = None,
                json: Any = None, headers: dict | None = None) -> Any:
        url = path if path.startswith("http") else BASE + path
        with httpx.Client(timeout=30) as client:
            for attempt in range(4):
                resp = client.request(method, url, params=params, json=json,
                                      headers=self._headers(headers))
                if resp.status_code in (429, 503, 504):
                    time.sleep(min(int(resp.headers.get("Retry-After", 2 ** attempt)), 60))
                    continue
                resp.raise_for_status()
                return resp.json() if resp.content else None
        raise RuntimeError(f"Graph: troppi tentativi per {method} {path}")

    def get_all(self, path: str, **kw) -> list[dict]:
        out, data = [], self.request("GET", path, **kw)
        while data:
            out += data.get("value", [])
            nxt = data.get("@odata.nextLink")
            data = self.request("GET", nxt) if nxt else None
        return out


class DryRunGraph:
    """Non invia nulla: logga e simula le risposte di Graph."""

    def __init__(self) -> None:
        self._ids = itertools.count(1)
        self.calls: list[tuple[str, str, Any]] = []

    def request(self, method, path, *, params=None, json=None, headers=None):
        self.calls.append((method, path, json))
        log.info("[dry-run] %s %s %s", method, path, json if method != "GET" else params)
        if method == "POST" and path.endswith("/messages"):
            n = next(self._ids)
            return {"id": f"dry-{n}-{uuid.uuid4().hex[:6]}", "conversationId": f"dry-conv-{n}",
                    "body": {"content": ""}}
        if method == "POST" and path.endswith(("/createReplyAll", "/createReply")):
            return {"id": f"dry-reply-{next(self._ids)}", "body": {"content": ""}}
        if method == "GET":
            return {"value": []}
        return None

    def get_all(self, path, **kw):
        return self.request("GET", path, **kw)["value"]


def get_graph():
    return Graph() if settings.graph_mode == "graph" else DryRunGraph()
