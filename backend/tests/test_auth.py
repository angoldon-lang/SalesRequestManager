"""Autenticazione locale: admin predefinito, cambio password obbligatorio, blocco account, token."""
import pytest
from sqlalchemy import text

from app.config import settings
from app.models import AppUser
from app.services.bootstrap import ensure_default_admin

API = "/api/v1"
DEFAULT = settings.default_admin_password


@pytest.fixture
def local(client, db, monkeypatch):
    """Modalità produzione: niente header di sviluppo, solo login con password."""
    monkeypatch.setattr(settings, "auth_disabled", False)
    monkeypatch.setattr(settings, "auth_mode", "local")
    ensure_default_admin(db)
    return client


def login(c, user, pw):
    return c.post(f"{API}/auth/login", json={"username": user, "password": pw})


def bearer(c, user, pw):
    r = login(c, user, pw)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def admin_session(c, new_pw="Nuova-Password-1"):
    """Login con la password predefinita + cambio obbligatorio; ritorna gli header dell'admin operativo."""
    h = bearer(c, "admin", DEFAULT)
    r = c.post(f"{API}/auth/change-password", headers=h, json={"current_password": DEFAULT, "new_password": new_pw})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_config_endpoint_is_public(client):
    assert client.get(f"{API}/auth/config").json() == {"mode": "dev"}


def test_default_admin_created_once(local, db):
    u = db.query(AppUser).filter_by(username="admin").one()
    assert u.role.value == "ADMIN" and u.must_change_password and u.is_active
    assert DEFAULT not in u.password_hash and u.password_hash.startswith("scrypt$")   # mai in chiaro
    assert ensure_default_admin(db) is False                                          # idempotente
    assert db.query(AppUser).count() == 1


def test_default_admin_recreated_only_if_no_usable_admin(local, db):
    db.execute(text("UPDATE app_users SET password_hash=NULL"))
    db.commit()
    assert ensure_default_admin(db) is True       # nessun admin può accedere: ripristino
    assert db.query(AppUser).filter_by(role="ADMIN").count() == 1


def test_requests_without_token_are_rejected(local):
    assert local.get(f"{API}/requests").status_code == 401
    assert local.get(f"{API}/requests", headers={"Authorization": "Bearer falso"}).status_code == 401
    assert local.get(f"{API}/auth/config").status_code == 200        # pubblico


def test_wrong_credentials_generic_message(local):
    a = login(local, "admin", "sbagliata!!")
    b = login(local, "inesistente", "sbagliata!!")
    assert a.status_code == b.status_code == 401 and a.json() == b.json()    # non rivela se l'utente esiste


def test_forced_password_change_flow(local):
    r = login(local, "admin", DEFAULT)
    assert r.status_code == 200 and r.json()["must_change_password"] is True
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert local.get(f"{API}/me", headers=h).json()["must_change_password"] is True      # /me ok
    blocked = local.get(f"{API}/requests", headers=h)
    assert blocked.status_code == 403 and blocked.json()["detail"]["code"] == "PASSWORD_CHANGE_REQUIRED"
    assert local.get(f"{API}/users", headers=h).status_code == 403

    r1 = local.post(f"{API}/auth/change-password", headers=h, json={"current_password": "x" * 12, "new_password": "Valida-Password-9"})
    assert r1.status_code == 422
    for weak in ("corta", DEFAULT, "admin"):
        r2 = local.post(f"{API}/auth/change-password", headers=h, json={"current_password": DEFAULT, "new_password": weak})
        assert r2.status_code == 422, weak

    ok = local.post(f"{API}/auth/change-password", headers=h, json={"current_password": DEFAULT, "new_password": "Valida-Password-9"})
    assert ok.status_code == 200 and ok.json()["must_change_password"] is False
    h2 = {"Authorization": f"Bearer {ok.json()['access_token']}"}
    assert local.get(f"{API}/requests", headers=h2).status_code == 200
    assert local.get(f"{API}/requests", headers=h).status_code == 401           # vecchia sessione invalidata
    assert login(local, "admin", DEFAULT).status_code == 401                    # la predefinita non vale più
    assert login(local, "admin", "Valida-Password-9").status_code == 200


def test_lockout_after_repeated_failures_and_admin_unlock(local):
    admin = admin_session(local)
    local.post(f"{API}/users", headers=admin, json={
        "username": "anna", "full_name": "Anna", "email": "anna@az.it", "role": "SALES", "password": "Provvisoria-123"})
    for _ in range(5):
        assert login(local, "anna", "no-no-no-no").status_code == 401
    r = login(local, "anna", "Provvisoria-123")                  # anche la password giusta è rifiutata
    assert r.status_code == 429 and "Riprova" in r.json()["detail"]
    uid = next(u["id"] for u in local.get(f"{API}/users", headers=admin).json() if u["username"] == "anna")
    assert local.post(f"{API}/users/{uid}/reset-password", headers=admin, json={"new_password": "Altra-Provvisoria-1"}).status_code == 200
    assert login(local, "anna", "Altra-Provvisoria-1").status_code == 200


def test_admin_creates_users_who_must_change_password(local):
    admin = admin_session(local)
    # Sales senza email: rifiutato (l'email serve per il CC)
    r = local.post(f"{API}/users", headers=admin, json={"username": "luca", "full_name": "Luca", "role": "SALES", "password": "Provvisoria-123"})
    assert r.status_code == 422 and "email" in r.json()["detail"]["fields"]
    # password debole / nome utente duplicato
    assert local.post(f"{API}/users", headers=admin, json={"username": "luca", "full_name": "L", "email": "l@az.it", "role": "SALES", "password": "corta"}).status_code == 422
    ok = local.post(f"{API}/users", headers=admin, json={"username": "luca", "full_name": "Luca", "email": "luca@az.it", "role": "SALES", "password": "Provvisoria-123"})
    assert ok.status_code == 201 and ok.json()["must_change_password"] is True and "password" not in ok.json()
    assert local.post(f"{API}/users", headers=admin, json={"username": "LUCA", "full_name": "x", "email": "x@az.it", "role": "SALES", "password": "Provvisoria-123"}).status_code == 409

    h = bearer(local, "luca", "Provvisoria-123")
    assert local.get(f"{API}/requests", headers=h).status_code == 403                 # prima deve cambiarla
    new = local.post(f"{API}/auth/change-password", headers=h, json={"current_password": "Provvisoria-123", "new_password": "Mia-Password-2026"}).json()
    h = {"Authorization": f"Bearer {new['access_token']}"}
    assert local.get(f"{API}/requests", headers=h).status_code == 200
    assert local.get(f"{API}/users", headers=h).status_code == 403                    # non è admin
    # un Sales può essere scelto come agente e vede solo le sue richieste
    agents = local.get(f"{API}/agents", headers=h).json()
    assert [a["email"] for a in agents] == ["luca@az.it"]


def test_deactivated_user_session_is_closed(local):
    admin = admin_session(local)
    local.post(f"{API}/users", headers=admin, json={"username": "bob", "full_name": "Bob", "email": "bob@az.it", "role": "BACKOFFICE", "password": "Provvisoria-123"})
    h = bearer(local, "bob", "Provvisoria-123")
    uid = next(u["id"] for u in local.get(f"{API}/users", headers=admin).json() if u["username"] == "bob")
    local.patch(f"{API}/users/{uid}", headers=admin, json={"is_active": False})
    assert local.get(f"{API}/me", headers=h).status_code == 401
    assert login(local, "bob", "Provvisoria-123").status_code == 401


def test_last_admin_and_self_protection(local):
    admin = admin_session(local)
    me = local.get(f"{API}/me", headers=admin).json()
    assert local.patch(f"{API}/users/{me['id']}", headers=admin, json={"role": "SALES"}).status_code == 409
    assert local.patch(f"{API}/users/{me['id']}", headers=admin, json={"is_active": False}).status_code == 409
    # un secondo admin: ora si può declassare l'altro, ma non l'ultimo rimasto
    local.post(f"{API}/users", headers=admin, json={"username": "boss", "full_name": "Boss", "role": "ADMIN", "password": "Provvisoria-123"})
    boss = next(u["id"] for u in local.get(f"{API}/users", headers=admin).json() if u["username"] == "boss")
    assert local.patch(f"{API}/users/{boss}", headers=admin, json={"role": "BACKOFFICE"}).status_code == 200
    assert local.patch(f"{API}/users/{me['id']}", headers=admin, json={"full_name": "Nuovo Nome"}).status_code == 200


def test_migrated_user_without_password_cannot_login(local, db):
    db.add(AppUser(username="ex.agente", email="ex@az.it", full_name="Ex", role="SALES"))
    db.commit()
    assert login(local, "ex.agente", "qualunque-cosa").status_code == 401


def test_login_disabled_in_dev_mode(client):
    assert login(client, "admin", "x").status_code == 404
