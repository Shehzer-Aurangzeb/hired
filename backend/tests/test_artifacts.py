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
    # The gap is for an answer only; test_an_email_is_never_handed_the_gap says why.
    assert "excited" in prompt and "passion" in prompt  # the forbidden register
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


def test_the_register_is_checked_rather_than_only_asked_for(client, monkeypatch):
    """
    Told not to, granite wrote "a passion for creating robust applications".
    The profile's own list holds "passionate" and missed it by one suffix, so
    the tells are matched on the stem.
    """
    save_profile(client)
    written(monkeypatch, {"subject": "s", "body": "A passion for robust applications."})
    row = make_row(client)

    made = client.post(f"/api/applications/{row}/artifacts", json={"kind": "email"}).json()
    found = " ".join(f["message"] for f in made["flags"])

    assert "passion" in found and "robust" in found
    assert all(f["type"] == "warn" for f in made["flags"])


def test_a_clean_sentence_is_not_flagged(client, monkeypatch):
    """A guard that fires on everything is one you learn to ignore."""
    save_profile(client)
    written(
        monkeypatch,
        {"subject": "s", "body": "I designed the PostgreSQL schema and shipped it."},
    )
    row = make_row(client)

    made = client.post(f"/api/applications/{row}/artifacts", json={"kind": "email"}).json()
    assert made["flags"] == []


def test_an_email_is_never_handed_the_gap(client, monkeypatch):
    """
    Given it, granite wrote that the candidate had "some foundational experience
    with C# and .NET" — the thing it had just been told they lack. An email has
    no need of it and it is the riskiest input there is.
    """
    save_profile(client)
    seen = written(monkeypatch)
    row = make_row(client)

    client.post(f"/api/applications/{row}/artifacts", json={"kind": "email"})
    assert "Kubernetes in production" not in seen["prompt"]

    client.post(
        f"/api/applications/{row}/artifacts",
        json={"kind": "answer", "question": "What are you weakest at?"},
    )
    assert "Kubernetes in production" in seen["prompt"]
    assert "never as partial or foundational" in seen["prompt"]


def test_an_answer_is_told_what_the_company_said_about_itself(client, monkeypatch):
    """
    Forbidding the topic failed: asked why they wanted to work at a school
    payments company, the model wrote about its "mission of improving
    healthcare". Supplying the fact beats forbidding the subject.
    """
    save_profile(client)
    seen = written(monkeypatch)
    row = make_row(client, jd_text=f"{JD} Acme builds payroll software for restaurants.")

    client.post(
        f"/api/applications/{row}/artifacts",
        json={"kind": "answer", "question": "Why do you want to work here?"},
    )
    assert "WHAT THE COMPANY SAYS ABOUT ITSELF" in seen["prompt"]
    assert "Acme builds payroll software for restaurants." in seen["prompt"]
    assert "you may not go past it" in seen["prompt"]

    # An email gets none of it: there is no question to answer.
    client.post(f"/api/applications/{row}/artifacts", json={"kind": "email"})
    assert "WHAT THE COMPANY SAYS ABOUT ITSELF" not in seen["prompt"]


def test_a_rewrite_sends_the_draft_as_its_own_turn(client, monkeypatch):
    """
    A model treats what it said itself as its own and quoted text as background
    reading, so the draft goes back as a turn rather than inside the prompt.
    """
    save_profile(client)
    seen = {}

    def fake(prompt, schema, turns=None, local="never", good=None):
        seen["prompt"], seen["turns"] = prompt, turns
        return {"subject": "s", "body": "Shorter."}

    monkeypatch.setattr(artifacts, "generate_json", fake)
    row = make_row(client)

    client.post(
        f"/api/applications/{row}/artifacts",
        json={"kind": "email", "draft": "A long first attempt.", "change": "Make it shorter."},
    )

    assert seen["turns"] == [
        ("model", "A long first attempt."),
        ("user", "Make it shorter.\n\nWrite it again."),
    ]
    assert "A long first attempt." not in seen["prompt"]


def test_a_first_draft_has_no_turns(client, monkeypatch):
    save_profile(client)
    seen = {}

    def fake(prompt, schema, turns=None, local="never", good=None):
        seen["turns"] = turns
        return {"subject": "s", "body": "A first go."}

    monkeypatch.setattr(artifacts, "generate_json", fake)
    row = make_row(client)
    client.post(f"/api/applications/{row}/artifacts", json={"kind": "email"})
    assert seen["turns"] is None


def test_the_company_line_is_found_rather_than_sliced_off_the_front():
    """Half the postings open with the job board's furniture, not the company."""
    from app.tables import Application

    def said(company, jd):
        return artifacts.about(
            Application(company=company, role="", jd_text=jd, fit_score=0, fit_reasoning="")
        )

    chrome = (
        "Company logo for, Homebase. Homebase Senior Mobile Engineer I (Hybrid) "
        "Toronto, ON · Reposted 11 hours ago · Over 100 applicants. "
        "Hey, We're Homebase. Homebase is the everything app for hourly teams."
    )
    assert said("Homebase", chrome).startswith("Homebase is the everything app")
    assert "Reposted" not in said("Homebase", chrome)
    # Nothing beats chrome: the prompt then tells the model it knows nothing.
    assert said("Acme", "Senior Engineer. Toronto. Apply now.") == ""


def test_the_voice_leads_and_its_examples_are_marked_as_not_facts(client, monkeypatch):
    """
    A model matches a sample's register better than it follows a description of
    one. Handed a good example it will also reuse its content, so the examples
    say in the prompt that their facts belong to other applications.
    """
    save_profile(client)
    seen = written(monkeypatch)
    row = make_row(client)

    client.post(f"/api/applications/{row}/artifacts", json={"kind": "email"})
    prompt = seen["prompt"]

    assert prompt.startswith("HOW THEY WRITE")
    assert "not yours to reuse" in prompt
    assert "Stanley Paden" in prompt  # an example, not this application


def test_the_year_figure_comes_from_the_profile_not_this_file(client, monkeypatch):
    """
    Hard-coding "3.5 years" in a prompt makes a second source of truth that
    still says 3.5 the year it is four. His own summary carries the number.
    """
    import app.artifacts as module

    save_profile(client)
    seen = written(monkeypatch)
    row = make_row(client, summary_text="Front-end engineer with 3.5+ years in React.")

    client.post(f"/api/applications/{row}/artifacts", json={"kind": "email"})

    assert "3.5+ years in React" in seen["prompt"]
    assert "3.5" not in module.VOICE.replace("3.5 years in,", "")  # only the example
