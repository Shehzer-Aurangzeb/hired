"""
The source routes, and mostly the one branch that protects the data: a save
composed against a stale copy must be refused rather than silently win.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app import auth
from app.db import get_session
from app.settings import Settings

PASSWORD = "correct horse battery staple"
GOOD = "# Identity\nname: Test Person\n\n# Experience\n## Co\nrole: Dev\n\n### Thing\nclaim_boundary:\n  can_claim:\n    - built it\nbullets:\n  - id: b1\n    text: Shipped it\n"


@pytest.fixture
def client(monkeypatch):
    settings = Settings(secret_key="t", password_hash=auth.hash_password(PASSWORD))
    monkeypatch.setattr(auth, "get_settings", lambda: settings)
    auth.reset_gate()

    from app.main import app

    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)

    def session_override():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = session_override
    with TestClient(app) as client:
        client.post("/api/auth/login", json={"password": PASSWORD})
        yield client
    app.dependency_overrides.clear()
    auth.reset_gate()


def save(client, text, expected=None):
    return client.put(
        "/api/profile/source", json={"text": text, "expected_updated_at": expected}
    )


def test_everything_here_needs_a_session(client):
    client.post("/api/auth/logout")
    assert client.get("/api/profile/source").status_code == 401
    assert client.post("/api/profile/validate", json={"text": GOOD}).status_code == 401
    assert save(client, GOOD).status_code == 401


def test_empty_before_anything_is_saved(client):
    assert client.get("/api/profile/source").json() == {
        "text": "", "exists": False, "updated_at": None
    }


def test_save_then_read_back(client):
    saved = save(client, GOOD).json()
    assert saved["exists"] and saved["text"] == GOOD
    assert client.get("/api/profile/source").json() == saved
    # And the parsed view now answers from the same row.
    assert client.get("/api/profile").json()["identity"]["name"] == "Test Person"


def test_timestamp_is_marked_utc(client):
    """A naive timestamp is read as local time and shifts every relative date."""
    stamp = save(client, GOOD).json()["updated_at"]
    assert stamp.endswith("+00:00")


def test_a_file_that_does_not_parse_is_refused(client):
    response = save(client, "# Identity\nname: X\n- \"q\" trailing")
    assert response.status_code == 422
    assert response.json()["errors"][0]["line"] == 3
    # Nothing was written.
    assert client.get("/api/profile/source").json()["exists"] is False


def test_a_stale_save_is_refused_and_hands_back_the_current_copy(client):
    first = save(client, GOOD).json()
    newer = save(client, GOOD + "\n# Languages\n- name: English\n", first["updated_at"]).json()

    conflict = save(client, GOOD + "\n# Certifications\n- name: X\n", first["updated_at"])
    assert conflict.status_code == 409
    body = conflict.json()
    assert body["updated_at"] == newer["updated_at"]
    assert body["text"] == newer["text"]
    # The stale write did not land.
    assert client.get("/api/profile/source").json()["text"] == newer["text"]


def test_saving_with_no_token_over_an_existing_profile_is_a_conflict(client):
    """First-run setup sends no token, and must not be able to wipe a profile."""
    save(client, GOOD)
    assert save(client, "# Identity\nname: Someone Else\n").status_code == 409


def test_validate_does_not_write(client):
    result = client.post("/api/profile/validate", json={"text": GOOD}).json()
    assert result["ok"] and result["summary"]["bullets"] == 1
    assert client.get("/api/profile/source").json()["exists"] is False


def test_validate_reports_warnings_without_failing(client):
    text = GOOD.replace("claim_boundary:\n  can_claim:\n    - built it\n", "")
    result = client.post("/api/profile/validate", json={"text": text}).json()
    assert result["ok"] is True
    assert result["summary"]["missing_boundaries"] == 1
    assert "claim_boundary" in result["warnings"][0]["message"]
