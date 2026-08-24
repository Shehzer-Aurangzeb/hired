"""
The fit check.

No test here reaches the network. What is worth pinning is the shape around the
call: that a missing key reads as a setup problem, that a score outside the
range cannot render a broken meter, that nothing is written, and that the
context sent to the model carries the constraints rather than the CV.
"""

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app import auth, fit, model
from app.db import get_session
from app.profile_parser import parse_text
from app.profile_template import DEFAULT_TEMPLATE
from app.settings import Settings
from app.tables import Application, ProfileSource

PASSWORD = "correct horse battery staple"

JD = """Senior Front-End Engineer, Payments. Montreal, hybrid.
Required: 5+ years React, TypeScript, accessibility, design systems.
Experience running services on Kubernetes in production."""

ANSWER = {
    "parsed_jd": {
        "company": "Acme",
        "role": "Senior Front-End Engineer",
        "required_skills": [{"name": "React", "importance": 3}],
        "keywords": ["payments"],
    },
    "score": 6,
    "reasoning": "React and TypeScript line up. Kubernetes does not.",
    "gaps": ["Kubernetes in production"],
}


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
        client.engine = engine
        yield client
    app.dependency_overrides.clear()
    auth.reset_gate()


def save_profile(client, text=DEFAULT_TEMPLATE):
    with Session(client.engine) as session:
        session.add(ProfileSource(text=text))
        session.commit()


def answers(monkeypatch, payload):
    """Stand in for the model. Records the prompt so the context can be read."""
    sent = {}

    def fake(prompt, schema):
        sent["prompt"], sent["schema"] = prompt, schema
        return payload

    monkeypatch.setattr(fit, "generate_json", fake)
    return sent


# ---------- the route ----------


def test_it_needs_a_session(client):
    client.post("/api/auth/logout")
    assert client.post("/api/fit", json={"jd_text": JD}).status_code == 401


def test_no_profile_means_nothing_to_score_against(client):
    assert client.post("/api/fit", json={"jd_text": JD}).status_code == 404


def test_a_title_is_not_a_posting(client):
    save_profile(client)
    response = client.post("/api/fit", json={"jd_text": "Front-End Developer"})
    assert response.status_code == 422
    assert "requirements" in response.json()["detail"]


def test_the_happy_path(client, monkeypatch):
    save_profile(client)
    answers(monkeypatch, ANSWER)

    body = client.post("/api/fit", json={"jd_text": JD}).json()
    assert body["fit"]["score"] == 6
    assert body["fit"]["gaps"] == ["Kubernetes in production"]
    assert body["parsed_jd"]["company"] == "Acme"
    # Defaulted rather than absent, because the UI maps over these.
    assert body["parsed_jd"]["preferred_skills"] == []
    assert body["parsed_jd"]["years_required"] is None


def test_a_score_outside_the_range_is_clamped(client, monkeypatch):
    """Gemini has returned 55 for this request shape. A 55 renders as a broken meter."""
    save_profile(client)
    answers(monkeypatch, {**ANSWER, "score": 55})
    assert client.post("/api/fit", json={"jd_text": JD}).json()["fit"]["score"] == 10

    answers(monkeypatch, {**ANSWER, "score": 0})
    assert client.post("/api/fit", json={"jd_text": JD}).json()["fit"]["score"] == 1


def test_a_sparse_answer_still_renders(client, monkeypatch):
    """A missing array is what blanked the whole detail page once before."""
    save_profile(client)
    answers(monkeypatch, {"score": 4})
    body = client.post("/api/fit", json={"jd_text": JD}).json()
    assert body["fit"]["gaps"] == [] and body["fit"]["reasoning"] == ""
    assert body["parsed_jd"]["required_skills"] == []


def test_it_writes_nothing(client, monkeypatch):
    """Discard has to be free. Saving is a separate route and a separate decision."""
    save_profile(client)
    answers(monkeypatch, ANSWER)
    client.post("/api/fit", json={"jd_text": JD})
    with Session(client.engine) as session:
        assert session.exec(select(Application)).all() == []


def test_no_key_reads_as_a_setup_problem(client):
    """Not configured must not look like the model refused."""
    save_profile(client)
    response = client.post("/api/fit", json={"jd_text": JD})
    assert response.status_code == 503
    assert "configured" in response.json()["detail"]


# ---------- what the model is told ----------


def test_the_prompt_carries_the_constraints_not_the_cv(client, monkeypatch):
    save_profile(client)
    sent = answers(monkeypatch, ANSWER)
    client.post("/api/fit", json={"jd_text": JD})
    prompt = sent["prompt"]

    profile = parse_text(DEFAULT_TEMPLATE)
    assert JD in prompt
    # The constraints that turn an apparent match into a gap.
    assert "cannot_claim" in prompt and "skill_evidence" in prompt
    assert profile.gaps[0].skill in prompt
    assert profile.experience[0].projects[0].claim_boundary.cannot_claim[0] in prompt
    # Nothing here decides what to print, so bullet text is dead weight.
    assert profile.experience[0].projects[0].bullets[0].text not in prompt


def test_the_context_spans_both_project_lists():
    profile = parse_text(DEFAULT_TEMPLATE)
    ids = [p["id"] for p in fit.context(profile)["projects"]]
    assert ids == [p.id for p in profile.all_projects()]
    assert "side-project" in ids


def test_the_schema_asks_for_a_one_to_ten_score():
    score = fit.SCHEMA["properties"]["score"]
    assert (score["minimum"], score["maximum"]) == (1, 10)


def test_skill_importance_is_clamped_to_the_three_point_scale(client, monkeypatch):
    """Gemini answers 5 on this scale, and the tooltip prints the number."""
    save_profile(client)
    answers(
        monkeypatch,
        {**ANSWER, "parsed_jd": {"required_skills": [{"name": "React", "importance": 5}]}},
    )
    body = client.post("/api/fit", json={"jd_text": JD}).json()
    assert body["parsed_jd"]["required_skills"][0]["importance"] == 3


# ---------- the model client ----------


def test_the_client_refuses_before_it_calls(monkeypatch):
    """No key means no request at all, rather than a 400 from Google."""
    monkeypatch.setattr(model, "get_settings", lambda: Settings(secret_key="t"))

    def explode(*args, **kwargs):
        raise AssertionError("should not have reached the network")

    monkeypatch.setattr(model.httpx, "post", explode)
    with pytest.raises(HTTPException) as error:
        model.generate_json("anything", {})
    assert error.value.status_code == 503
