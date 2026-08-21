"""
The security-shaped bits: the hash round trip, that a session is actually
required, and that the lockout expires on its own. That last one has bitten this
project once already, in the mock, where a counter that only reset on success
made the correct password unusable forever.
"""

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

from app import auth
from app.db import get_session
from app.settings import Settings

PASSWORD = "correct horse battery staple"


@pytest.fixture
def client(monkeypatch):
    hashed = auth.hash_password(PASSWORD)
    settings = Settings(secret_key="test-secret", password_hash=hashed)
    monkeypatch.setattr(auth, "get_settings", lambda: settings)
    auth.reset_gate()

    from app.main import app

    # An in-memory database, or the suite reads and could write the developer's
    # real hired.db. StaticPool keeps every connection on the same one.
    from sqlalchemy.pool import StaticPool

    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)

    def session_override():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = session_override
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()
    auth.reset_gate()


# ---------- hashing ----------


def test_hash_round_trip():
    hashed = auth.hash_password(PASSWORD)
    assert auth.verify_password(PASSWORD, hashed)
    assert not auth.verify_password(PASSWORD + " ", hashed)
    # The password must not be recoverable from what we store.
    assert PASSWORD not in hashed


def test_every_hash_is_salted():
    assert auth.hash_password(PASSWORD) != auth.hash_password(PASSWORD)


def test_a_broken_hash_locks_rather_than_opens():
    for junk in ["", "not-a-hash", "scrypt$x$y$z$q$w", "bcrypt$1$2$3$4$5"]:
        assert not auth.verify_password(PASSWORD, junk)


# ---------- the session ----------


def test_session_starts_signed_out(client):
    assert client.get("/api/auth/session").json() == {"authenticated": False}


def test_protected_routes_refuse_without_a_session(client):
    for path in ["/api/profile", "/api/profile/template"]:
        assert client.get(path).status_code == 401, path


def test_login_then_the_same_routes_answer(client):
    assert client.post("/api/auth/login", json={"password": PASSWORD}).status_code == 200
    assert client.get("/api/auth/session").json() == {"authenticated": True}
    assert client.get("/api/profile/template").status_code == 200
    # 404 rather than 401: signed in, and there is simply no profile saved.
    assert client.get("/api/profile").status_code == 404


def test_logout_closes_the_door_again(client):
    client.post("/api/auth/login", json={"password": PASSWORD})
    client.post("/api/auth/logout")
    assert client.get("/api/auth/session").json() == {"authenticated": False}
    assert client.get("/api/profile/template").status_code == 401


def test_wrong_password_is_401_and_grants_nothing(client):
    response = client.post("/api/auth/login", json={"password": "wrong"})
    assert response.status_code == 401
    assert client.get("/api/profile/template").status_code == 401


def test_no_configured_hash_refuses_everyone(client, monkeypatch):
    monkeypatch.setattr(auth, "get_settings", lambda: Settings(secret_key="t"))
    assert client.post("/api/auth/login", json={"password": PASSWORD}).status_code == 503


# ---------- the lockout ----------


def test_lockout_after_repeated_failures(client):
    for _ in range(auth.MAX_ATTEMPTS - 1):
        assert client.post("/api/auth/login", json={"password": "wrong"}).status_code == 401

    locked = client.post("/api/auth/login", json={"password": "wrong"})
    assert locked.status_code == 429
    assert locked.json()["retry_after"] == auth.BASE_LOCKOUT
    assert locked.headers["Retry-After"] == str(auth.BASE_LOCKOUT)

    # The right password is refused too, or the lockout would be pointless.
    assert client.post("/api/auth/login", json={"password": PASSWORD}).status_code == 429


def test_the_lockout_expires_on_its_own(client, monkeypatch):
    """A counter that only clears on success locks out the correct password."""
    for _ in range(auth.MAX_ATTEMPTS):
        client.post("/api/auth/login", json={"password": "wrong"})
    assert client.post("/api/auth/login", json={"password": PASSWORD}).status_code == 429

    now = __import__("time").monotonic()
    monkeypatch.setattr(auth.time, "monotonic", lambda: now + auth.BASE_LOCKOUT + 1)
    assert client.post("/api/auth/login", json={"password": PASSWORD}).status_code == 200


def test_each_lockout_is_longer_than_the_last(client, monkeypatch):
    clock = {"now": __import__("time").monotonic()}
    monkeypatch.setattr(auth.time, "monotonic", lambda: clock["now"])

    waits = []
    for _ in range(3):
        for _ in range(auth.MAX_ATTEMPTS):
            response = client.post("/api/auth/login", json={"password": "wrong"})
        waits.append(response.json()["retry_after"])
        clock["now"] += waits[-1] + 1

    assert waits == [30, 60, 120]


def test_a_correct_password_clears_the_escalation(client):
    for _ in range(auth.MAX_ATTEMPTS - 1):
        client.post("/api/auth/login", json={"password": "wrong"})
    assert client.post("/api/auth/login", json={"password": PASSWORD}).status_code == 200
    assert auth._gate.failures == 0 and auth._gate.lockouts == 0
