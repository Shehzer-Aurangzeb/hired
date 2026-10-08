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
        # Lets the pruning test backdate rows directly.
        client.engine = engine
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
        "text": "", "exists": False, "updated_at": None, "version": None
    }


def test_save_then_read_back(client):
    saved = save(client, GOOD).json()
    assert saved["exists"] and saved["text"] == GOOD
    assert client.get("/api/profile/source").json() == saved
    assert client.get("/api/profile").json()["identity"]["name"] == "Test Person"


def test_timestamp_is_marked_utc(client):
    """A naive timestamp is read as local time and shifts every relative date."""
    stamp = save(client, GOOD).json()["updated_at"]
    assert stamp.endswith("+00:00")


def test_a_file_that_does_not_parse_is_refused(client):
    response = save(client, "# Identity\nname: X\n- \"q\" trailing")
    assert response.status_code == 422
    assert response.json()["errors"][0]["line"] == 3
    assert client.get("/api/profile/source").json()["exists"] is False


def test_a_stale_save_is_refused_and_hands_back_the_current_copy(client):
    first = save(client, GOOD).json()
    newer = save(client, GOOD + "\n# Languages\n- name: English\n", first["updated_at"]).json()

    conflict = save(client, GOOD + "\n# Certifications\n- name: X\n", first["updated_at"])
    assert conflict.status_code == 409
    body = conflict.json()
    assert body["updated_at"] == newer["updated_at"]
    assert body["text"] == newer["text"]
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


# ---------- editing one bullet from the Browse screen ----------

WITH_BULLETS = """# Identity
name: N

# Experience
## Devnito
role: Engineer

### Dedicate
id: dedicate
label: A platform
  # This comment is why the edit is surgery and not a round trip.
claim_boundary:
  cannot_claim:
    - The backend
bullets:
  - id: dedicate-cache
    priority: 1
    tags: [frontend, performance]
    text: Cut repeat API calls by an estimated 50% with a tiered cache
      across 18 query patterns in TanStack Query.
    short: Cut repeat API calls by an estimated 50%.
    metric:
      value: 'estimated 50% fewer repeat API calls'
      source: estimated
  - id: dedicate-auth
    priority: 2
    text: Built the Auth0 flow.
"""


def test_editing_a_bullet_changes_one_line_and_nothing_else(client):
    from app.profile_parser import parse_text, replace_bullet_text

    edited = replace_bullet_text(
        WITH_BULLETS, "dedicate-cache", "Cut repeat API calls by an estimated 60%."
    )
    before, after = WITH_BULLETS.split("\n"), edited.split("\n")
    # Comments outside the edited bullet survive.
    assert [line for line in before if "This comment" in line]
    assert [line for line in after if "This comment" in line]

    bullet = next(
        b for p in parse_text(edited).all_projects() for b in p.bullets if b.id == "dedicate-cache"
    )
    assert bullet.text == "Cut repeat API calls by an estimated 60%."
    assert bullet.priority == 1 and bullet.tags == ["frontend", "performance"]
    assert bullet.short == "Cut repeat API calls by an estimated 50%."
    assert bullet.metric and bullet.metric.source == "estimated"
    other = next(
        b for p in parse_text(edited).all_projects() for b in p.bullets if b.id == "dedicate-auth"
    )
    assert other.text == "Built the Auth0 flow."


def test_an_apostrophe_in_a_bullet_does_not_break_the_file(client):
    from app.profile_parser import parse_text, replace_bullet_text

    said = "Built the client's dashboard, and it's live."
    edited = replace_bullet_text(WITH_BULLETS, "dedicate-auth", said)
    bullet = next(
        b for p in parse_text(edited).all_projects() for b in p.bullets if b.id == "dedicate-auth"
    )
    assert bullet.text == said


def test_editing_a_bullet_through_the_api(client):
    stamp = client.put(
        "/api/profile/source", json={"text": WITH_BULLETS, "expected_updated_at": None}
    ).json()["updated_at"]

    response = client.patch(
        "/api/profile/bullets/dedicate-auth",
        json={"text": "Built the full Auth0 flow behind a BFF pattern.", "expected_updated_at": stamp},
    )
    assert response.status_code == 200
    assert "Built the full Auth0 flow behind a BFF pattern." in response.json()["text"]

    profile = client.get("/api/profile").json()
    texts = [b["text"] for p in profile["experience"][0]["projects"] for b in p["bullets"]]
    assert "Built the full Auth0 flow behind a BFF pattern." in texts


def test_a_bullet_edit_cannot_skip_the_conflict_check(client):
    client.put("/api/profile/source", json={"text": WITH_BULLETS, "expected_updated_at": None})
    response = client.patch(
        "/api/profile/bullets/dedicate-auth",
        json={"text": "Written against a copy that moved.", "expected_updated_at": "2020-01-01T00:00:00+00:00"},
    )
    assert response.status_code == 409


def test_editing_a_bullet_that_is_not_there(client):
    client.put("/api/profile/source", json={"text": WITH_BULLETS, "expected_updated_at": None})
    stamp = client.get("/api/profile/source").json()["updated_at"]
    gone = client.patch(
        "/api/profile/bullets/ghost", json={"text": "x", "expected_updated_at": stamp}
    )
    assert gone.status_code == 404
    empty = client.patch(
        "/api/profile/bullets/dedicate-auth", json={"text": "   ", "expected_updated_at": stamp}
    )
    assert empty.status_code == 422


# ---------- version history ----------


def test_every_save_appends_a_version(client):
    save(client, GOOD)
    first = client.get("/api/profile/source").json()
    save(client, GOOD + "\n", first["updated_at"])

    versions = client.get("/api/profile/versions").json()
    assert [v["version"] for v in versions] == [2, 1]
    assert [v["current"] for v in versions] == [True, False]


def test_an_old_version_can_be_read_back(client):
    save(client, GOOD)
    one = client.get("/api/profile/source").json()
    save(client, GOOD + "\n# Awards\n", one["updated_at"])

    assert client.get("/api/profile/versions/1").json()["text"] == GOOD


def test_restore_appends_rather_than_rewinding(client):
    """Rewinding would erase the record of the mistake it is undoing."""
    save(client, GOOD)
    one = client.get("/api/profile/source").json()
    save(client, GOOD + "\n# Awards\n", one["updated_at"])
    two = client.get("/api/profile/source").json()

    back = client.post(
        "/api/profile/versions/1/restore",
        json={"expected_updated_at": two["updated_at"]},
    ).json()

    assert back["text"] == GOOD
    assert back["version"] == 3
    assert [v["version"] for v in client.get("/api/profile/versions").json()] == [3, 2, 1]


def test_restoring_against_a_stale_token_conflicts(client):
    save(client, GOOD)
    one = client.get("/api/profile/source").json()
    save(client, GOOD + "\n# Awards\n", one["updated_at"])

    response = client.post(
        "/api/profile/versions/1/restore",
        json={"expected_updated_at": one["updated_at"]},
    )
    assert response.status_code == 409


def test_a_pruned_version_says_so(client):
    save(client, GOOD)
    assert client.get("/api/profile/versions/99").status_code == 404
    assert "pruned" in client.get("/api/profile/versions/99").json()["detail"]


def test_pruning_keeps_the_floor_however_old_everything_is(client):
    """The newest VERSIONS_KEPT survive whatever their age; recent ones survive too."""
    from datetime import timedelta

    from app.tables import VERSIONS_KEPT, ProfileSource, now

    save(client, GOOD)                       # v1, written now
    with Session(client.engine) as session:  # v2..v9, long past the window
        for n in range(8):
            session.add(
                ProfileSource(text=f"{GOOD}\n# {n}\n", updated_at=now() - timedelta(days=400))
            )
        session.commit()

    latest = client.get("/api/profile/source").json()
    save(client, GOOD + "\n# fresh\n", latest["updated_at"])   # v10, and prunes

    kept = [v["version"] for v in client.get("/api/profile/versions").json()]

    assert kept[:VERSIONS_KEPT] == [10, 9, 8, 7, 6]
    # v1 is recent, so it survives outside the floor.
    assert 1 in kept
    assert [v for v in (2, 3, 4, 5) if v in kept] == []
    assert kept[0] == 10 and client.get("/api/profile/versions").json()[0]["current"]


def test_the_diff_reads_as_what_restoring_would_do(client):
    """Current first: "-" is what restoring loses, "+" what it brings back."""
    save(client, GOOD)
    one = client.get("/api/profile/source").json()
    save(client, GOOD.replace("Shipped it", "Shipped it twice"), one["updated_at"])

    diff = client.get("/api/profile/versions/1/diff").json()

    assert diff["from_version"] == 2 and diff["to_version"] == 1
    assert diff["added"] == 1 and diff["removed"] == 1
    body = {line["op"]: line["text"] for line in diff["lines"] if line["op"] in "+-"}
    assert "twice" in body["-"]       # what the current version says
    assert "twice" not in body["+"]   # what v1 would bring back


def test_the_diff_carries_context_not_the_whole_file(client):
    save(client, GOOD)
    one = client.get("/api/profile/source").json()
    save(client, GOOD.replace("Shipped it", "Shipped it twice"), one["updated_at"])

    diff = client.get("/api/profile/versions/1/diff").json()
    assert len(diff["lines"]) < len(GOOD.splitlines())


def test_an_identical_version_diffs_to_nothing(client):
    save(client, GOOD)
    one = client.get("/api/profile/source").json()
    save(client, GOOD, one["updated_at"])

    diff = client.get("/api/profile/versions/1/diff").json()
    assert diff["lines"] == [] and diff["added"] == 0 and diff["removed"] == 0


def test_diffing_a_pruned_version_says_so(client):
    save(client, GOOD)
    assert client.get("/api/profile/versions/99/diff").status_code == 404
