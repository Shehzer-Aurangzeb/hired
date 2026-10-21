import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app import auth, fit, model, taxonomy
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

    def fake(prompt, schema, turns=None, local="never", **_):
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
    # The score and the gaps are worked out in code, so the model's own
    # numbers in ANSWER are ignored. It only wrote the sentences.
    assert 2 <= body["fit"]["score"] <= 9
    assert body["fit"]["reasoning"] == ANSWER["reasoning"]
    assert body["parsed_jd"]["company"] == "Acme"
    assert body["parsed_jd"]["preferred_skills"] == []
    assert body["parsed_jd"]["years_required"] is None


def test_the_model_cannot_move_the_score_or_add_a_gap(client, monkeypatch):
    """It reported the candidate was missing React. Now it is not asked."""
    save_profile(client)
    answers(monkeypatch, {**ANSWER, "score": 55, "gaps": ["invented"]})
    high = client.post("/api/fit", json={"jd_text": JD}).json()["fit"]

    answers(monkeypatch, {**ANSWER, "score": 0, "gaps": ["also invented"]})
    low = client.post("/api/fit", json={"jd_text": JD}).json()["fit"]

    assert high["score"] == low["score"] and 2 <= high["score"] <= 9
    assert "invented" not in high["gaps"] and "also invented" not in low["gaps"]


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


def test_the_scoring_prompt_carries_the_verdict_not_the_profile(client, monkeypatch):
    """
    The model is handed what was worked out, not the material to work it out
    from. Given the profile it decided the candidate lacked React.
    """
    save_profile(client)
    sent = answers(monkeypatch, ANSWER)
    client.post("/api/fit", json={"jd_text": JD})
    prompt = sent["prompt"]

    profile = parse_text(DEFAULT_TEMPLATE)
    assert "THIS LIST IS COMPLETE" in prompt and "SCORE:" in prompt
    assert "Never add a gap" in prompt
    # Nothing to re-derive from: no raw profile, no bullets, no posting.
    assert "cannot_claim" not in prompt and "skill_evidence" not in prompt
    assert profile.experience[0].projects[0].bullets[0].text not in prompt


def test_the_context_spans_both_project_lists():
    profile = parse_text(DEFAULT_TEMPLATE)
    ids = [p["id"] for p in fit.context(profile)["projects"]]
    assert ids == [p.id for p in profile.all_projects()]
    assert "side-project" in ids


def test_the_scoring_schema_can_only_return_prose():
    """A field the model cannot return is a field it cannot get wrong."""
    assert set(fit.SCORE_SCHEMA["properties"]) == {"reasoning"}


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
    monkeypatch.setattr(model, "loaded", lambda settings: False)
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
    # Without this ollama defaults to 4096 and silently truncates the prompt
    # from the front, so scoring and selection arrived with no profile in them.
    assert sent["options"]["num_ctx"] == settings.ollama_ctx
    assert sent["options"]["num_ctx"] >= 12288


def test_a_tired_mac_is_not_asked_to_run_a_model(monkeypatch):
    settings = Settings(secret_key="t", ollama_model="granite3.3:8b")
    monkeypatch.setattr(model, "get_settings", lambda: settings)
    monkeypatch.setattr(model, "unhealthy", lambda: "only 4% of memory is free")
    monkeypatch.setattr(model, "loaded", lambda settings: False)

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


def test_a_skill_with_no_evidence_row_still_counts_as_had(client, monkeypatch):
    """A skill with no evidence projects is breadth, never depth, never a gap."""
    from app.models import ParsedJd, RequiredSkill

    profile = parse_text(DEFAULT_TEMPLATE)
    listed = profile.skills[0].items[0]
    met, unmet, _score = fit.requirements(
        profile, ParsedJd(required_skills=[RequiredSkill(name=listed, importance=3)])
    )
    assert unmet == [] and len(met) == 1 and met[0].startswith(listed)


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
    answers(monkeypatch, {"reasoning": "ok", "parsed_jd": {
        "required_skills": [{"name": "Svelte", "importance": 3}]}})

    body = client.post("/api/fit", json={"jd_text": JD}).json()

    # Svelte exists only in version 2. Scored against v1 it would be a gap.
    assert body["fit"]["gaps"] == []


def test_a_listed_skill_is_not_a_gap():
    """
    Git and Node.js sat in skills with no skill_evidence row, and one posting
    came back scoring them as gaps. A listed skill is claimed, not missing.
    """
    from app.models import ParsedJd, RequiredSkill

    profile = parse_text(DEFAULT_TEMPLATE)
    every = [item for row in profile.skills for item in row.items]
    _met, unmet, _score = fit.requirements(
        profile,
        ParsedJd(required_skills=[RequiredSkill(name=n, importance=3) for n in every]),
    )
    assert unmet == []


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


def test_scoring_asks_the_local_model_when_gemini_will_not_answer(client, monkeypatch):
    """The route must pass local="fallback", not only support it."""
    asked = []

    def generate_json(prompt, schema, turns=None, local="never", **_):
        asked.append(local)
        if local == "first":
            return {"company": "Acme", "role": "Dev",
                    "required_skills": [], "preferred_skills": []}
        return {"score": 7, "reasoning": "fine", "gaps": []}

    monkeypatch.setattr(fit, "generate_json", generate_json)
    save_profile(client)
    response = client.post("/api/fit", json={"jd_text": "x" * 200})

    assert response.status_code == 200
    assert asked == ["first", "fallback"]


def test_an_empty_answer_is_asked_again_and_says_so(monkeypatch):
    """A posting with no requirements in it is valid JSON and not an answer."""
    settings = Settings(secret_key="t", gemini_api_key="g")
    monkeypatch.setattr(model, "get_settings", lambda: settings)
    replies = iter([{"required_skills": []}, {"required_skills": [{"name": "React"}]}])
    monkeypatch.setattr(model, "_gemini", lambda *a, **k: next(replies))

    answer = model.generate_json("p", {}, good=lambda a: bool(a["required_skills"]))

    assert answer["required_skills"] == [{"name": "React"}]
    assert "asked again" in model.notice.get()


def test_empty_twice_is_an_error_not_a_third_try(monkeypatch):
    settings = Settings(secret_key="t", gemini_api_key="g")
    monkeypatch.setattr(model, "get_settings", lambda: settings)
    tries = []
    monkeypatch.setattr(model, "_gemini",
                        lambda *a, **k: tries.append(1) or {"required_skills": []})

    with pytest.raises(HTTPException) as error:
        model.generate_json("p", {}, good=lambda a: bool(a["required_skills"]))

    assert len(tries) == 2
    assert error.value.status_code == 502


def test_a_good_answer_is_not_retried_and_leaves_no_notice(monkeypatch):
    settings = Settings(secret_key="t", gemini_api_key="g")
    monkeypatch.setattr(model, "get_settings", lambda: settings)
    tries = []
    monkeypatch.setattr(model, "_gemini",
                        lambda *a, **k: tries.append(1) or {"required_skills": ["React"]})

    model.generate_json("p", {}, good=lambda a: bool(a["required_skills"]))

    assert len(tries) == 1
    assert model.notice.get() == ""


# ---------- code-first gap derivation ----------


def _needs(*names: str):
    from app.models import ParsedJd, RequiredSkill

    return ParsedJd(required_skills=[RequiredSkill(name=n, importance=3) for n in names])


def test_either_half_of_a_choice_satisfies_it():
    """
    KEV asked for "TypeScript or JavaScript with React, or C# with .NET". The
    model called it a gap for a developer with three years of React.
    """
    profile = parse_text(DEFAULT_TEMPLATE)
    _met, unmet, _score = fit.requirements(
        profile,
        _needs("Working knowledge of TypeScript or JavaScript with React, or C# with .NET"),
    )
    assert unmet == []


def test_a_degree_requirement_is_answered_by_the_education_section():
    """The profile holds an M.S.; the model reported a two-year diploma as a gap."""
    profile = parse_text(DEFAULT_TEMPLATE)
    met, unmet, _score = fit.requirements(
        profile, _needs("Related two-year diploma in computer technology")
    )
    assert met and unmet == []


def test_postgresql_answers_a_requirement_for_sql():
    """Whole-word matching missed it; PostgreSQL is a SQL database."""
    profile = parse_text(DEFAULT_TEMPLATE)
    assert any(
        "postgres" in item.casefold() for row in profile.skills for item in row.items
    ), "fixture no longer has PostgreSQL"

    _met, unmet, _score = fit.requirements(
        profile, _needs("Basic understanding of relational databases and SQL")
    )
    assert unmet == []


def test_a_sibling_tool_is_a_near_miss_not_a_match():
    """
    Zustand is not Redux and AWS is not Azure. Counting a sibling as met is how
    a CV claims experience its owner cannot defend.
    """
    from app import taxonomy

    profile = parse_text(DEFAULT_TEMPLATE)
    have = taxonomy.implied(set(), ["Zustand"])
    assert "redux" not in have

    _met, unmet, _score = fit.requirements(profile, _needs("Redux"))
    assert len(unmet) == 1 and unmet[0].startswith("Redux")


def test_a_disposition_counts_neither_way():
    profile = parse_text(DEFAULT_TEMPLATE)
    met, unmet, score = fit.requirements(
        profile, _needs("Clear written communication", "Ability to work independently")
    )
    assert met == [] and unmet == [] and score == 5


def test_a_non_compete_is_not_a_skill():
    profile = parse_text(DEFAULT_TEMPLATE)
    met, unmet, _score = fit.requirements(
        profile, _needs("Non-disclosure, non-compete agreement")
    )
    assert met == [] and unmet == []


def test_a_gap_the_person_listed_themselves_wins_over_a_word_match():
    profile = parse_text(DEFAULT_TEMPLATE)
    named = profile.gaps[0].skill
    _met, unmet, _score = fit.requirements(profile, _needs(named))
    assert len(unmet) == 1 and "your own gaps list says" in unmet[0]


def test_the_reasoning_is_cut_to_three_sentences():
    """The prompt asked for three; measured output ran to eleven."""
    long = " ".join(f"Sentence number {n}." for n in range(1, 12))
    assert fit._three_sentences(long) == (
        "Sentence number 1. Sentence number 2. Sentence number 3."
    )
    assert fit._three_sentences("Just one.") == "Just one."
    assert fit._three_sentences("") == ""


def test_a_met_requirement_names_what_backs_it():
    """
    Handed "Any exposure to Azure or another cloud platform" as met, the model
    wrote that the candidate had used Azure. They had not. A requirement's own
    words are not evidence of anything, so the backing skill travels with it.
    """
    profile = parse_text(DEFAULT_TEMPLATE)
    react = next(
        item for row in profile.skills for item in row.items if item.casefold() == "react"
    )
    met, _unmet, _score = fit.requirements(
        profile, _needs(f"Exposure to Pascal or {react}")
    )
    assert len(met) == 1
    backing = met[0].split(" — ", 1)[1]
    assert react in backing and "Pascal" not in backing


def test_a_trait_the_reader_labelled_counts_neither_way():
    """
    Government postings ask for "coaching conflict resolution" and "considering
    broader trends". No regex of named dispositions keeps up, so the reader
    labels each requirement as it reads the posting.
    """
    from app.models import ParsedJd, RequiredSkill

    profile = parse_text(DEFAULT_TEMPLATE)
    jd = ParsedJd(
        required_skills=[
            RequiredSkill(name="Coaching conflict resolution", importance=3, kind="trait"),
            RequiredSkill(name="Considering broader trends", importance=3, kind="trait"),
        ]
    )
    met, unmet, score = fit.requirements(profile, jd)
    assert met == [] and unmet == [] and score == 5


def test_a_trait_does_not_drag_the_score_down():
    """Six unscorable competencies took one posting from 8 to 6."""
    from app.models import ParsedJd, RequiredSkill

    profile = parse_text(DEFAULT_TEMPLATE)
    react = next(
        item for row in profile.skills for item in row.items if item.casefold() == "react"
    )
    alone = fit.requirements(
        profile, ParsedJd(required_skills=[RequiredSkill(name=react, importance=3)])
    )[2]
    padded = fit.requirements(
        profile,
        ParsedJd(
            required_skills=[RequiredSkill(name=react, importance=3)]
            + [
                RequiredSkill(name=f"Soft competency {n}", importance=3, kind="trait")
                for n in range(6)
            ]
        ),
    )[2]
    assert alone == padded


def test_a_requirement_read_twice_is_listed_once():
    """One posting was read as wanting monitoring twice."""
    from app.models import ParsedJd, RequiredSkill

    profile = parse_text(DEFAULT_TEMPLATE)
    _met, unmet, _score = fit.requirements(
        profile,
        ParsedJd(
            required_skills=[RequiredSkill(name="Kubernetes monitoring", importance=3)] * 3
        ),
    )
    assert len(unmet) == 1


def test_the_local_call_asks_for_greedy_decoding(monkeypatch):
    """
    ollama defaults temperature to 0.8. Reading one posting three times gave
    15, 18 and 23 requirements, and the gaps moved with them.
    """
    settings = Settings(secret_key="t", ollama_model="granite3.3:8b")
    monkeypatch.setattr(model, "get_settings", lambda: settings)
    monkeypatch.setattr(model, "unhealthy", lambda: None)
    sent = {}

    def post(url, **kwargs):
        sent.update(kwargs["json"])
        return _reply(200, OLLAMA_OK)

    monkeypatch.setattr(model._LOCAL, "post", post)
    model.generate_json("anything", {"type": "object"}, local="first")

    assert sent["options"]["temperature"] == 0


def test_the_same_requirement_written_two_ways_counts_once():
    """"React" beside "React.js" is one requirement, and counting it twice moves the score."""
    from app.generate import _wants
    from app.models import ParsedJd, RequiredSkill

    jd = ParsedJd(
        required_skills=[
            RequiredSkill(name="React", importance=3),
            RequiredSkill(name="React.js", importance=3),
            RequiredSkill(name="Node.js", importance=2),
            RequiredSkill(name="NodeJS", importance=2),
        ]
    )
    assert [name for name, _w, _t, _k in _wants(jd)] == ["React", "Node.js"]


def test_a_dotted_spelling_is_not_a_gap():
    """"React.js" tokenised to "react.j", met nothing, and read as a gap."""
    profile = parse_text(DEFAULT_TEMPLATE)
    _met, unmet, _score = fit.requirements(profile, _needs("React.js"))
    assert unmet == []


# ---------- choosing a model from the screen ----------


def test_the_models_route_lists_what_this_machine_can_serve(client, monkeypatch):
    monkeypatch.setattr(fit, "available", lambda settings: ["granite3.3:8b", "qwen2.5:7b"])
    body = client.get("/api/models").json()
    assert body["models"] == ["granite3.3:8b", "qwen2.5:7b"]


def test_a_model_this_machine_does_not_have_is_refused(client, monkeypatch):
    """The name is handed to ollama; a request body does not decide what runs."""
    from app import model as M

    monkeypatch.setattr(M, "available", lambda settings: ["granite3.3:8b"])
    save_profile(client)
    answers(monkeypatch, ANSWER)

    bad = client.post("/api/fit", json={"jd_text": JD, "model": "anything-i-like"})
    assert bad.status_code == 422

    assert client.post("/api/fit", json={"jd_text": JD, "model": "granite3.3:8b"}).status_code == 200


def test_a_chosen_model_answers_and_never_falls_back(monkeypatch):
    """
    A comparison answered by a model you did not choose is worthless, so a
    named model is binding: its failure is an error, not a quiet Gemini answer.
    """
    settings = Settings(
        secret_key="t", gemini_api_key="g", ollama_model="granite3.3:8b"
    )
    monkeypatch.setattr(model, "get_settings", lambda: settings)
    monkeypatch.setattr(model, "available", lambda s: ["granite3.3:8b", "qwen2.5:7b"])
    monkeypatch.setattr(model, "unhealthy", lambda: None)
    monkeypatch.setattr(model, "_gemini", lambda *a, **k: pytest.fail("asked gemini"))
    asked = []

    def local(prompt, schema, s, turns=None):
        asked.append(s.ollama_model)
        return {"ok": 1}

    monkeypatch.setattr(model, "_ollama", local)
    model.choose("qwen2.5:7b")
    # local="never" is the strictest routing there is; a named model outranks it.
    model.generate_json("p", {})

    assert asked == ["qwen2.5:7b"]
    model.pick.set("")


def test_choosing_gemini_by_name_skips_the_local_model(monkeypatch):
    settings = Settings(
        secret_key="t", gemini_api_key="g", ollama_model="granite3.3:8b"
    )
    monkeypatch.setattr(model, "get_settings", lambda: settings)
    monkeypatch.setattr(model, "available", lambda s: ["granite3.3:8b", settings.gemini_model])
    monkeypatch.setattr(model, "_ollama", lambda *a, **k: pytest.fail("asked the local model"))
    monkeypatch.setattr(model, "_gemini", lambda *a, **k: {"ok": 1})

    model.choose(settings.gemini_model)
    # local="first" would normally reach for the local model before Gemini.
    assert model.generate_json("p", {}, local="first") == {"ok": 1}
    model.pick.set("")


def test_choosing_nothing_keeps_the_configured_routing(monkeypatch):
    settings = Settings(secret_key="t", gemini_api_key="g", ollama_model="granite3.3:8b")
    monkeypatch.setattr(model, "get_settings", lambda: settings)
    monkeypatch.setattr(model, "unhealthy", lambda: None)
    order = []
    monkeypatch.setattr(model, "_ollama", lambda *a, **k: order.append("local") or {})
    monkeypatch.setattr(model, "_gemini", lambda *a, **k: order.append("gemini") or {})

    model.choose("")
    model.generate_json("p", {}, local="first")
    model.generate_json("p", {})

    assert order == ["local", "gemini"]


def test_a_model_already_in_memory_is_not_refused_for_memory(monkeypatch):
    """
    The floor is about whether to load a model, not whether to use one. Resident,
    a second call allocates nothing — and refusing it made the rewrite loop
    impossible, since the first call was what used the memory.
    """
    settings = Settings(secret_key="t", ollama_model="mistral-nemo:12b")
    monkeypatch.setattr(model, "get_settings", lambda: settings)
    monkeypatch.setattr(model, "unhealthy", lambda: "only 12% of memory is free")
    monkeypatch.setattr(model._LOCAL, "post", lambda url, **kw: _reply(200, OLLAMA_OK))

    monkeypatch.setattr(model, "loaded", lambda s: True)
    assert model.generate_json("p", {}, local="first") == {"score": 7}

    # Not loaded, the floor still applies: that call would allocate 8GB.
    monkeypatch.setattr(model, "loaded", lambda s: False)
    with pytest.raises(HTTPException) as refused:
        model.generate_json("p", {}, local="first")
    assert refused.value.status_code == 503


def test_loaded_reads_what_ollama_has_resident(monkeypatch):
    settings = Settings(secret_key="t", ollama_model="granite3.3:8b")

    def ps(url, **kwargs):
        assert url.endswith("/api/ps")
        return _reply(200, {"models": [{"name": "granite3.3:8b"}]})

    monkeypatch.setattr(model._LOCAL, "get", ps)
    assert model.loaded(settings) is True
    assert model.loaded(Settings(secret_key="t", ollama_model="qwen2.5:7b")) is False


def test_the_taxonomy_sees_through_punctuation():
    """"Built it in TypeScript." implied nothing: the full stop broke the match."""
    from app import taxonomy
    from app.generate import _terms

    for text in ("Built it in TypeScript.", "TypeScript, with React.", "(TypeScript)"):
        assert "javascript" in taxonomy.implied(_terms(text), [text]), text
    # A stray lowercase word inside another is still not a match.
    assert "cloud" not in taxonomy.implied(_terms("Moved DNS to Cloudflare."), ["Moved DNS to Cloudflare."])


def test_a_phrase_in_the_taxonomy_backs_only_the_whole_phrase():
    """"cross-platform" answered "cloud platform" and "source control" answered "open source"."""
    from app.generate import _terms

    have = taxonomy.implied(set(), ["React Native", "Git"])
    assert taxonomy.backs(_terms("cross-platform apps"), have)
    assert taxonomy.backs(_terms("version control"), have)
    assert not taxonomy.backs(_terms("exposure to Azure or another cloud platform"), have)
    assert not taxonomy.backs(_terms("open source contribution"), have)
    page = _terms("Reviewed code and opened a second checkout page.")
    assert not taxonomy.backs(_terms("internship, co-op, or open source contribution with code review"), page)
