"""The email and the form answer: what the model is handed, and what it may not add."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app import artifacts, auth
from app.db import get_session
from app.profile_parser import parse_text
from app.profile_template import DEFAULT_TEMPLATE
from app.settings import Settings
from app.tables import Application, ProfileSource

PASSWORD = "correct horse battery staple"

JD = """Front-End Developer, Montreal. Build customer-facing React interfaces in
TypeScript, contribute to a shared component library. Required: 3+ years React."""


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
    with TestClient(app) as made:
        made.post("/api/auth/login", json={"password": PASSWORD})
        made.engine = engine
        yield made
    app.dependency_overrides.clear()
    auth.reset_gate()


def save_profile(client, text=DEFAULT_TEMPLATE):
    with Session(client.engine) as session:
        session.add(ProfileSource(text=text))
        session.commit()


def make_row(client, **over):
    """A scored posting with a CV already generated for it."""
    body = {
        "company": "Acme",
        "role": "Front-End Developer",
        "jd_text": JD,
        "jd_parsed": {"required_skills": [{"name": "React", "importance": 3, "kind": "skill"}]},
        "fit_score": 8,
        "fit_reasoning": "ok",
        "gaps": ["Kubernetes in production"],
        "selected_bullets": [
            {"id": "a", "text": "Cut p75 load time by 40% on a React table.",
             "project_name": "Ledgerline"},
            {"id": "b", "text": "Built a 40-component library in Storybook.",
             "project_name": "Northwind"},
        ],
        **over,
    }
    return client.post("/api/applications", json=body).json()["id"]


def written(monkeypatch, reply=None):
    """Stand in for the model and keep the prompt it was given."""
    seen = {}

    def fake(prompt, schema, turns=None, local="never", good=None):
        seen["prompt"] = prompt
        return reply or {"subject": "Front-End Developer", "body": "A plain sentence."}

    monkeypatch.setattr(artifacts, "generate_json", fake)
    return seen


def test_the_prompt_carries_the_evidence_and_the_posting(client, monkeypatch):
    """
    Everything there is to say arrives already decided. The model joins it; it
    is never asked to work out what is true.
    """
    save_profile(client)
    seen = written(monkeypatch)
    row = make_row(client)

    client.post(f"/api/applications/{row}/artifacts", json={"kind": "email"})
    prompt = seen["prompt"]

    assert "Cut p75 load time by 40% on a React table." in prompt
    assert "Acme" in prompt and "Front-End Developer" in prompt
    assert "Kubernetes in production" in prompt           # the honest gap
    assert "excited" in prompt and "passionate" in prompt  # the forbidden register
    # Nothing to invent around: no raw posting, no profile, no bullet pool.
    assert JD not in prompt
    assert "cannot_claim" not in prompt and "skill_evidence" not in prompt


def test_the_strongest_evidence_leads_and_the_rest_is_left_out(client, monkeypatch):
    """Three at most, most relevant first. A recruiter skims and a form counts characters."""
    save_profile(client)
    seen = written(monkeypatch)
    row = make_row(
        client,
        selected_bullets=[
            {"id": "x", "text": "Wrote the deployment runbook."},
            {"id": "y", "text": "Shipped a React and TypeScript design system."},
            {"id": "z", "text": "Organised the team offsite."},
            {"id": "w", "text": "Ran the React migration for the billing app."},
        ],
    )

    client.post(f"/api/applications/{row}/artifacts", json={"kind": "email"})
    listed = seen["prompt"].split("IN THEIR OWN WORDS:")[1].split("\n\n")[0]

    assert listed.count("\n- ") == artifacts.MOST_BULLETS
    assert "React and TypeScript design system" in listed
    assert "offsite" not in listed, "the least relevant bullet should be dropped"


def test_an_answer_needs_its_question(client, monkeypatch):
    save_profile(client)
    written(monkeypatch)
    row = make_row(client)

    blank = client.post(f"/api/applications/{row}/artifacts", json={"kind": "answer"})
    assert blank.status_code == 422

    ok = client.post(
        f"/api/applications/{row}/artifacts",
        json={"kind": "answer", "question": "Why this role?"},
    )
    assert ok.status_code == 201


def test_a_posting_with_no_cv_has_nothing_to_write_from(client, monkeypatch):
    """The bullets that printed are the evidence; without them there is none."""
    save_profile(client)
    written(monkeypatch)
    row = make_row(client, selected_bullets=[])

    refused = client.post(f"/api/applications/{row}/artifacts", json={"kind": "email"})
    assert refused.status_code == 422
    assert "Generate one first" in refused.json()["detail"]


def test_it_is_kept_on_the_row_with_the_model_that_wrote_it(client, monkeypatch):
    save_profile(client)
    written(monkeypatch)
    row = make_row(client)

    made = client.post(
        f"/api/applications/{row}/artifacts", json={"kind": "email"}
    ).json()
    assert made["body"] == "A plain sentence."

    with Session(client.engine) as session:
        kept = session.get(Application, row).artifacts
    assert len(kept) == 1
    assert kept[0]["kind"] == "email" and kept[0]["created_at"]
    assert "flags" not in kept[0]  # a verdict on today's text, not a stored fact


def test_a_banned_word_is_flagged_rather_than_silently_sent(client, monkeypatch):
    """The same guard the CV gets. It cannot catch an invented fact; it catches
    the words you never say."""
    save_profile(client)
    banned = parse_text(DEFAULT_TEMPLATE).rules.banned_words[0]

    written(monkeypatch, {"subject": "s", "body": f"I am {banned} about this role."})
    row = make_row(client)

    made = client.post(
        f"/api/applications/{row}/artifacts", json={"kind": "email"}
    ).json()
    assert [f["type"] for f in made["flags"]] == ["block"]


def test_an_unknown_kind_is_refused(client, monkeypatch):
    save_profile(client)
    written(monkeypatch)
    row = make_row(client)
    assert (
        client.post(f"/api/applications/{row}/artifacts", json={"kind": "poem"}).status_code
        == 422
    )


def test_the_row_hands_back_what_was_written(client, monkeypatch):
    """Kept on the row is not enough; the detail page has to be able to read it."""
    save_profile(client)
    written(monkeypatch)
    row = make_row(client)

    client.post(f"/api/applications/{row}/artifacts", json={"kind": "email"})
    fetched = client.get(f"/api/applications/{row}").json()

    assert len(fetched["artifacts"]) == 1
    assert fetched["artifacts"][0]["kind"] == "email"


def test_the_timestamp_is_marked_utc(client, monkeypatch):
    """A naive string reads as local time, and a fresh artifact showed "in 4 hours"."""
    from datetime import datetime

    save_profile(client)
    written(monkeypatch)
    row = make_row(client)

    made = client.post(f"/api/applications/{row}/artifacts", json={"kind": "email"}).json()
    when = datetime.fromisoformat(made["created_at"])

    assert when.tzinfo is not None, "unmarked, so the browser will read it as local"
    assert when <= datetime.now(when.tzinfo)
