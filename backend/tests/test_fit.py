import httpx
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
    """
    Stand in for the model. Fit makes two calls, extraction then scoring, so one
    payload covers both and each call takes the keys its schema declares.
    """
    sent = {}

    def fake(prompt, schema, turns=None, local="never"):
        key = "extract" if local == "first" else "score"
        sent[key] = {"prompt": prompt, "schema": schema}
        sent["prompt"], sent["schema"] = prompt, schema   # the scoring call, last
        if local == "first":
            return payload.get("parsed_jd") or {}
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
    assert body["parsed_jd"]["preferred_skills"] == []
    assert body["parsed_jd"]["years_required"] is None


def test_a_score_outside_the_range_is_clamped(client, monkeypatch):
    save_profile(client)
    answers(monkeypatch, {**ANSWER, "score": 55})
    assert client.post("/api/fit", json={"jd_text": JD}).json()["fit"]["score"] == 10

    answers(monkeypatch, {**ANSWER, "score": 0})
    assert client.post("/api/fit", json={"jd_text": JD}).json()["fit"]["score"] == 1


def test_a_sparse_answer_still_renders(client, monkeypatch):
    save_profile(client)
    answers(monkeypatch, {"score": 4})
    body = client.post("/api/fit", json={"jd_text": JD}).json()
    assert body["fit"]["gaps"] == [] and body["fit"]["reasoning"] == ""
    assert body["parsed_jd"]["required_skills"] == []


def test_it_writes_nothing(client, monkeypatch):
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
    assert "cannot_claim" in prompt and "skill_evidence" in prompt
    assert profile.gaps[0].skill in prompt
    assert profile.experience[0].projects[0].claim_boundary.cannot_claim[0] in prompt
    # Bullet text is not needed for fit, so it is left out.
    assert profile.experience[0].projects[0].bullets[0].text not in prompt


def test_the_context_spans_both_project_lists():
    profile = parse_text(DEFAULT_TEMPLATE)
    ids = [p["id"] for p in fit.context(profile)["projects"]]
    assert ids == [p.id for p in profile.all_projects()]
    assert "side-project" in ids


def test_the_schema_asks_for_a_one_to_ten_score():
    score = fit.SCORE_SCHEMA["properties"]["score"]
    assert (score["minimum"], score["maximum"]) == (1, 10)


def test_skill_importance_is_clamped_to_the_three_point_scale(client, monkeypatch):
    save_profile(client)
    answers(
        monkeypatch,
        {**ANSWER, "parsed_jd": {"required_skills": [{"name": "React", "importance": 5}]}},
    )
    body = client.post("/api/fit", json={"jd_text": JD}).json()
    assert body["parsed_jd"]["required_skills"][0]["importance"] == 3


# ---------- the model client ----------


def test_the_client_refuses_before_it_calls(monkeypatch):
    monkeypatch.setattr(model, "get_settings", lambda: Settings(secret_key="t"))

    def explode(*args, **kwargs):
        raise AssertionError("should not have reached the network")

    monkeypatch.setattr(model._CLIENT, "post", explode)
    with pytest.raises(HTTPException) as error:
        model.generate_json("anything", {})
    assert error.value.status_code == 503


def _reply(status, payload):
    return httpx.Response(status, json=payload, request=httpx.Request("POST", "http://t"))


OLLAMA_OK = {"message": {"content": '{"score": 7}'}}
GEMINI_OK = {"candidates": [{"content": {"parts": [{"text": '{"score": 3}'}]}}]}


def calls(monkeypatch, settings, *replies):
    """Answer each POST with the next reply, and record where each one went."""
    monkeypatch.setattr(model, "get_settings", lambda: settings)
    seen = []
    pending = list(replies)

    def post(url, **kwargs):
        seen.append(url)
        return pending.pop(0)

    monkeypatch.setattr(model._CLIENT, "post", post)
    return seen


def test_gemini_is_tried_first_when_its_key_is_set(monkeypatch):
    settings = Settings(secret_key="t", gemini_api_key="g")
    seen = calls(monkeypatch, settings, _reply(200, GEMINI_OK))

    assert model.generate_json("anything", {}) == {"score": 3}
    assert len(seen) == 1 and seen[0].startswith(model.GEMINI)


def test_a_loaded_gemini_does_not_fall_through_to_the_local_model(monkeypatch):
    """
    The local model reads postings well and judges profiles badly. Asked to
    score, it returned a bullet id as a project and described someone else.
    Scoring and selection are Gemini or an error.
    """
    settings = Settings(secret_key="t", gemini_api_key="g", ollama_model="granite3.3:8b")
    calls(monkeypatch, settings, _reply(429, {}))
    monkeypatch.setattr(model, "unhealthy", lambda: None)
    monkeypatch.setattr(model._LOCAL, "post", lambda *a, **k: pytest.fail("asked the local model"))

    with pytest.raises(HTTPException) as error:
        model.generate_json("anything", {})
    assert error.value.status_code == 429


def test_without_a_fallback_geminis_error_is_the_answer(monkeypatch):
    settings = Settings(secret_key="t", gemini_api_key="g")
    calls(monkeypatch, settings, _reply(429, {}))

    with pytest.raises(HTTPException) as error:
        model.generate_json("anything", {})
    assert error.value.status_code == 429


def test_reading_a_posting_goes_to_the_local_model(monkeypatch):
    settings = Settings(secret_key="t", gemini_api_key="g", ollama_model="granite3.3:8b")
    monkeypatch.setattr(model, "get_settings", lambda: settings)
    monkeypatch.setattr(model, "unhealthy", lambda: None)
    monkeypatch.setattr(model._LOCAL, "post", lambda url, **kw: _reply(200, OLLAMA_OK))
    monkeypatch.setattr(model, "_gemini", lambda *a, **k: pytest.fail("asked gemini"))

    assert model.generate_json("anything", {}, local="first") == {"score": 7}


def test_a_dead_local_model_still_lets_the_posting_be_read(monkeypatch):
    """Gemini reads a posting worse, not not at all."""
    settings = Settings(secret_key="t", gemini_api_key="g", ollama_model="granite3.3:8b")
    monkeypatch.setattr(model, "get_settings", lambda: settings)
    monkeypatch.setattr(model, "unhealthy", lambda: "the Mac is thermally throttling")
    monkeypatch.setattr(model, "_gemini", lambda *a, **k: {"score": 7})

    assert model.generate_json("anything", {}, local="first") == {"score": 7}


def test_the_local_call_asks_for_the_schema_and_no_thinking(monkeypatch):
    """Reasoning tokens cost the same as useful ones, and generation is the expense."""
    settings = Settings(secret_key="t", ollama_model="granite3.3:8b")
    monkeypatch.setattr(model, "get_settings", lambda: settings)
    monkeypatch.setattr(model, "unhealthy", lambda: None)
    sent = {}

    def post(url, **kwargs):
        sent.update(kwargs["json"])
        return _reply(200, OLLAMA_OK)

    monkeypatch.setattr(model._LOCAL, "post", post)
    model.generate_json("anything", {"type": "object"}, local="first")

    assert sent["model"] == "granite3.3:8b"
    assert sent["think"] is False
    assert sent["format"] == {"type": "object"}


def test_a_tired_mac_is_not_asked_to_run_a_model(monkeypatch):
    settings = Settings(secret_key="t", ollama_model="granite3.3:8b")
    monkeypatch.setattr(model, "get_settings", lambda: settings)
    monkeypatch.setattr(model, "unhealthy", lambda: "only 4% of memory is free")

    with pytest.raises(HTTPException) as error:
        model.generate_json("anything", {}, local="first")
    assert error.value.status_code == 503
    assert "4% of memory" in error.value.detail


# ---------- applying twice to the same employer ----------


def _file(client, company, role="Front-End Developer", status="applied"):
    with Session(client.engine) as session:
        session.add(
            Application(
                company=company, role=role, jd_text=JD, jd_parsed={},
                fit_score=7, fit_reasoning="", status=status,
            )
        )
        session.commit()


def test_a_first_look_at_a_company_reports_nothing_seen(client, monkeypatch):
    save_profile(client)
    answers(monkeypatch, ANSWER)
    assert client.post("/api/fit", json={"jd_text": JD}).json()["seen"] == []


def test_an_earlier_application_to_the_same_company_comes_back(client, monkeypatch):
    save_profile(client)
    answers(monkeypatch, ANSWER)
    _file(client, "Acme", role="Backend Developer", status="rejected")

    seen = client.post("/api/fit", json={"jd_text": JD}).json()["seen"]
    assert [(s["role"], s["status"]) for s in seen] == [("Backend Developer", "rejected")]


def test_the_match_ignores_case_and_surrounding_space(client, monkeypatch):
    save_profile(client)
    answers(monkeypatch, {**ANSWER, "parsed_jd": {**ANSWER["parsed_jd"], "company": "  acme "}})
    _file(client, "ACME")
    assert len(client.post("/api/fit", json={"jd_text": JD}).json()["seen"]) == 1


def test_a_different_company_is_not_a_duplicate(client, monkeypatch):
    save_profile(client)
    answers(monkeypatch, ANSWER)
    _file(client, "Acme Corp")  # exact match only
    assert client.post("/api/fit", json={"jd_text": JD}).json()["seen"] == []


def test_an_unnamed_company_does_not_match_every_blank_row(client, monkeypatch):
    save_profile(client)
    answers(monkeypatch, {**ANSWER, "parsed_jd": {**ANSWER["parsed_jd"], "company": ""}})
    _file(client, "")
    assert client.post("/api/fit", json={"jd_text": JD}).json()["seen"] == []


def test_the_fit_check_still_writes_nothing(client, monkeypatch):
    save_profile(client)
    answers(monkeypatch, ANSWER)
    client.post("/api/fit", json={"jd_text": JD})
    with Session(client.engine) as session:
        assert session.exec(select(Application)).all() == []


def test_the_prompt_says_what_an_unpinned_skill_means(client, monkeypatch):
    """A skill with no evidence projects is breadth, never depth."""
    save_profile(client)
    sent = answers(monkeypatch, ANSWER)
    client.post("/api/fit", json={"jd_text": JD})

    assert "empty evidence list" in sent["prompt"]
    assert "never as depth" in sent["prompt"]


def test_it_scores_against_the_newest_version(client, monkeypatch):
    """
    profile_source is an append-only log. An unordered first() returns v1, so
    every edit since version history landed would be invisible to scoring.
    """
    save_profile(client)
    save_profile(
        client,
        DEFAULT_TEMPLATE.replace("[React, TypeScript, RxJS", "[React, TypeScript, Svelte, RxJS", 1),
    )
    sent = answers(monkeypatch, {"score": 5, "reasoning": "ok", "gaps": [], "parsed_jd": {}})

    client.post("/api/fit", json={"jd_text": JD})

    assert "Svelte" in sent["prompt"]


def test_a_listed_skill_is_not_a_gap(monkeypatch):
    """
    Git and Node.js sat in skills with no skill_evidence row, and one posting
    came back scoring them as gaps. A listed skill is claimed, not missing.
    """
    from app import fit

    assert "no skill_evidence entry is claimed but not" in fit.INSTRUCTIONS
    assert "do not\n  report it as a gap" in fit.INSTRUCTIONS


def test_the_posting_is_read_before_it_is_scored(client, monkeypatch):
    """
    Extraction runs on its own, locally, with no profile competing for attention.
    Scoring then gets the list rather than re-reading the raw posting.
    """
    save_profile(client)
    sent = answers(monkeypatch, {"score": 7, "reasoning": "ok", "gaps": [],
                                 "parsed_jd": {"company": "C", "role": "R",
                                               "required_skills": [], "preferred_skills": []}})
    client.post("/api/fit", json={"jd_text": JD})

    assert "PROFILE:" not in sent["extract"]["prompt"]      # nothing to distract it
    assert JD[:40] in sent["extract"]["prompt"]
    assert "PROFILE:" in sent["score"]["prompt"]
    assert "WHAT THE POSTING ASKS FOR:" in sent["score"]["prompt"]
    assert "parsed_jd" not in sent["score"]["schema"]["properties"]


def test_extraction_prefers_the_local_model(monkeypatch):
    """Thoroughness beats speed when reading a posting; 90% against 49%."""
    from app import model
    from app.settings import Settings

    settings = Settings(secret_key="t", gemini_api_key="g", ollama_model="granite3.3:8b")
    monkeypatch.setattr(model, "get_settings", lambda: settings)
    monkeypatch.setattr(model, "unhealthy", lambda: None)
    tried = []
    monkeypatch.setattr(model, "_gemini", lambda *a, **k: tried.append("gemini") or {})
    monkeypatch.setattr(model, "_ollama", lambda *a, **k: tried.append("ollama") or {})

    model.generate_json("p", {}, local="first")
    model.generate_json("p", {})

    assert tried == ["ollama", "gemini"]


def test_a_busy_gemini_does_not_block_a_score(monkeypatch):
    """"Try again later" is useless on the day you are applying."""
    settings = Settings(secret_key="t", gemini_api_key="g", ollama_model="granite3.3:8b")
    monkeypatch.setattr(model, "get_settings", lambda: settings)
    monkeypatch.setattr(model, "unhealthy", lambda: None)
    monkeypatch.setattr(model, "_gemini", lambda *a, **k: (_ for _ in ()).throw(
        HTTPException(502, "high demand")))
    monkeypatch.setattr(model, "_ollama", lambda *a, **k: {"score": 7})

    assert model.generate_json("p", {}, local="fallback") == {"score": 7}
    assert model.served.get() == "granite3.3:8b"   # named, so it can be distrusted


def test_choosing_bullets_never_falls_back(monkeypatch):
    """A fabricated page is worse than no page."""
    settings = Settings(secret_key="t", gemini_api_key="g", ollama_model="granite3.3:8b")
    monkeypatch.setattr(model, "get_settings", lambda: settings)
    monkeypatch.setattr(model, "_gemini", lambda *a, **k: (_ for _ in ()).throw(
        HTTPException(502, "high demand")))
    monkeypatch.setattr(model, "_ollama", lambda *a, **k: pytest.fail("asked the local model"))

    with pytest.raises(HTTPException):
        model.generate_json("p", {})
