"""Ask: the guard and the splicer."""

import pathlib

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app import ask, auth
from app.ask import Change
from app.db import get_session
from app.profile_parser import ProfileError, parse_text
from app.settings import Settings
from app.tables import ProfileSource

PASSWORD = "correct horse battery staple"

PROFILE = """# Identity
name: Test Person

---

# Skills
- line: Frontend
  items: [React, TypeScript,
    Redux]
- line: Backend
  items: [Node.js]

---

# Skill Evidence
- name: React
  years: 3.5
  last_used: 2026-08
  level: advanced
  context: professional
  evidence: [thing]

---

# Experience
## Co
role: Dev

### Thing
claim_boundary:
  can_claim:
    - built it
  cannot_claim:
    - never ran it at scale
bullets:
  - id: thing-one
    text: Shipped the thing
"""


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
    with Session(engine) as session:
        session.add(ProfileSource(text=PROFILE))
        session.commit()

    def session_override():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = session_override
    with TestClient(app) as client:
        client.post("/api/auth/login", json={"password": PASSWORD})
        yield client
    app.dependency_overrides.clear()
    auth.reset_gate()


def answers(monkeypatch, payload):
    """Stand in for the model, and hand back the prompt it was given."""
    sent = {}

    def fake(prompt, schema, turns=None):
        sent["prompt"] = prompt
        sent["turns"] = turns or []
        # Ask makes two calls: the op, then that op's fields.
        changes = payload.get("changes") or []
        if "op" in schema["properties"]:
            return {
                "op": changes[0]["op"] if changes else "ask",
                "reply": payload.get("reply", ""),
                "questions": payload.get("questions", []),
            }
        return {"changes": [{k: v for k, v in c.items() if k != "op"} for c in changes]}

    monkeypatch.setattr(ask, "generate_json", fake)
    return sent


def say(client, message, history=None):
    return client.post(
        "/api/profile/ask", json={"message": message, "history": history or []}
    )


# ---------- the splicer ----------


def test_a_new_skill_entry_lands_in_its_section(client, monkeypatch):
    answers(
        monkeypatch,
        {
            "reply": "Recorded Redux.",
            "changes": [
                {
                    "op": "add_skill_evidence",
                    "target": "Redux",
                    "level": "working",
                    "last_used": "2026-06",
                    "evidence": ["thing"],
                }
            ],
        },
    )
    body = say(client, "I used Redux on Thing").json()

    assert body["text"] is not None
    profile = parse_text(body["text"])
    redux = next(s for s in profile.skill_evidence if s.name == "Redux")
    assert redux.level == "working" and redux.evidence == ["thing"]
    assert len(profile.skill_evidence) == 2


def test_the_rest_of_the_file_is_byte_for_byte_the_same(client, monkeypatch):
    """A splice, not a rewrite."""
    answers(
        monkeypatch,
        {
            "reply": "ok",
            "changes": [{"op": "add_skill_evidence", "target": "Redux", "level": "familiar"}],
        },
    )
    body = say(client, "redux, familiar").json()

    before = PROFILE.split("\n")
    after = body["text"].split("\n")
    added = [line for line in after if line not in before]
    assert added == ["- name: Redux", "  level: familiar"]


def test_an_item_joins_a_skills_row_that_wraps(client, monkeypatch):
    """The list spans two lines in the fixture."""
    answers(
        monkeypatch,
        {
            "reply": "ok",
            "changes": [{"op": "add_skill_item", "line": "Frontend", "target": "Zustand"}],
        },
    )
    body = say(client, "add zustand to frontend").json()

    profile = parse_text(body["text"])
    frontend = next(row for row in profile.skills if row.line == "Frontend")
    assert "Zustand" in frontend.items
    assert next(row for row in profile.skills if row.line == "Backend").items == ["Node.js"]


def test_a_bullet_gets_an_id_the_app_chose(client, monkeypatch):
    answers(
        monkeypatch,
        {
            "reply": "ok",
            "changes": [
                {
                    "op": "add_bullet",
                    "project_id": "thing",
                    "text": "Built the search index from scratch",
                }
            ],
        },
    )
    body = say(client, "add a bullet about the search index").json()

    profile = parse_text(body["text"])
    ids = [b.id for p in profile.all_projects() for b in p.bullets]
    assert ids == ["thing-one", "thing-built-the"]


def test_updating_an_entry_keeps_the_fields_it_did_not_mention(client, monkeypatch):
    """Correcting the level must not quietly drop the years."""
    answers(
        monkeypatch,
        {
            "reply": "ok",
            "changes": [
                {"op": "update_skill_evidence", "target": "React", "level": "expert"}
            ],
        },
    )
    body = say(client, "React is expert now").json()

    react = next(s for s in parse_text(body["text"]).skill_evidence if s.name == "React")
    assert react.level == "expert"
    assert react.years == 3.5 and react.last_used == "2026-08"
    assert react.evidence == ["thing"]


# ---------- the guard ----------


def test_a_project_that_does_not_exist_is_refused(client, monkeypatch):
    answers(
        monkeypatch,
        {
            "reply": "ok",
            "changes": [
                {"op": "add_skill_evidence", "target": "Redux", "evidence": ["invented"]}
            ],
        },
    )
    body = say(client, "redux on invented").json()

    assert body["text"] is None
    assert "invented" in body["refused"][0]


def test_a_number_with_no_source_is_refused(client, monkeypatch):
    answers(
        monkeypatch,
        {
            "reply": "ok",
            "changes": [
                {
                    "op": "add_bullet",
                    "project_id": "thing",
                    "text": "Cut load time by 40%",
                }
            ],
        },
    )
    body = say(client, "add a bullet about performance").json()

    assert body["text"] is None
    assert "number" in body["refused"][0]


def test_an_estimate_has_to_say_so_in_the_bullet(client, monkeypatch):
    answers(
        monkeypatch,
        {
            "reply": "ok",
            "changes": [
                {
                    "op": "add_bullet",
                    "project_id": "thing",
                    "text": "Cut load time by 40%",
                    "metric_value": "40%",
                    "metric_source": "estimated",
                }
            ],
        },
    )
    body = say(client, "about 40 percent faster").json()

    assert body["text"] is None
    assert "estimated" in body["refused"][0]


def test_an_estimate_that_says_so_goes_through(client, monkeypatch):
    answers(
        monkeypatch,
        {
            "reply": "ok",
            "changes": [
                {
                    "op": "add_bullet",
                    "project_id": "thing",
                    "text": "Cut load time by an estimated 40% by deferring the bundle",
                    "metric_value": "40%",
                    "metric_source": "estimated",
                    "metric_method": "Lighthouse, before and after",
                }
            ],
        },
    )
    body = say(client, "roughly 40 percent, measured in lighthouse").json()

    bullet = parse_text(body["text"]).all_projects()[0].bullets[-1]
    assert bullet.metric.source == "estimated"
    assert "estimated" in bullet.text


def test_a_version_number_in_a_name_is_not_a_measurement(client, monkeypatch):
    """Auth0 and S3 are names, not metrics."""
    answers(
        monkeypatch,
        {
            "reply": "ok",
            "changes": [
                {
                    "op": "add_bullet",
                    "project_id": "thing",
                    "text": "Built the Auth0 flow behind a BFF pattern",
                }
            ],
        },
    )
    body = say(client, "add the auth0 bullet").json()
    assert body["text"] is not None


def test_an_operation_outside_the_list_is_refused(client, monkeypatch):
    answers(
        monkeypatch,
        {
            "reply": "ok",
            "changes": [{"op": "remove_cannot_claim", "target": "never ran it at scale"}],
        },
    )
    body = say(client, "drop that boundary").json()

    assert body["text"] is None
    assert "remove_cannot_claim" in body["refused"][0]
    assert "never ran it at scale" in PROFILE


def test_a_made_up_level_is_refused(client, monkeypatch):
    answers(
        monkeypatch,
        {
            "reply": "ok",
            "changes": [{"op": "add_skill_evidence", "target": "Redux", "level": "guru"}],
        },
    )
    assert "guru" in say(client, "redux guru").json()["refused"][0]


# ---------- the conversation ----------


def test_nothing_is_saved_until_it_is_confirmed(client, monkeypatch):
    answers(
        monkeypatch,
        {
            "reply": "ok",
            "changes": [{"op": "add_skill_evidence", "target": "Redux", "level": "working"}],
        },
    )
    say(client, "redux, working")

    assert client.get("/api/profile/source").json()["text"] == PROFILE
    assert len(client.get("/api/profile/versions").json()) == 1


def test_confirming_is_an_ordinary_save(client, monkeypatch):
    answers(
        monkeypatch,
        {
            "reply": "ok",
            "changes": [{"op": "add_skill_evidence", "target": "Redux", "level": "working"}],
        },
    )
    proposed = say(client, "redux, working").json()["text"]
    before = client.get("/api/profile/source").json()

    client.put(
        "/api/profile/source",
        json={"text": proposed, "expected_updated_at": before["updated_at"]},
    )

    versions = client.get("/api/profile/versions").json()
    assert [v["version"] for v in versions] == [2, 1]
    assert client.get("/api/profile/versions/1/diff").json()["removed"] == 2


def test_questions_come_back_with_no_changes(client, monkeypatch):
    answers(
        monkeypatch,
        {
            "reply": "Which projects used it?",
            "questions": ["Which projects used Redux?"],
            "changes": [],
        },
    )
    body = say(client, "I have used redux").json()

    assert body["text"] is None
    assert body["questions"] == ["Which projects used Redux?"]


def test_the_prompt_carries_the_file_the_history_and_real_bullets(client, monkeypatch):
    sent = answers(monkeypatch, {"reply": "ok", "changes": []})
    say(
        client,
        "and what about Zustand",
        [
            {"role": "you", "text": "I used Redux"},
            {"role": "ask", "text": "On which project?"},
        ],
    )

    prompt = sent["prompt"]
    assert "Shipped the thing" in prompt          # voice, from their own bullets
    assert "# Skill Evidence" in prompt           # the slice it needs
    assert sent["turns"] == [                     # a conversation, not a quoted transcript
        ("user", "I used Redux"),
        ("model", "On which project?"),
        ("user", "and what about Zustand"),
    ]


# ---------- splicing directly ----------


def test_adding_an_item_that_is_already_there_is_refused():
    with pytest.raises(ProfileError):
        ask._apply(PROFILE, Change(op="add_skill_item", line="Frontend", target="Redux"))


def test_a_colon_in_a_bullet_gets_quoted():
    """Unquoted, YAML reads it as a mapping."""
    out = ask._apply(
        PROFILE,
        Change(op="add_bullet", project_id="thing", text="Built the flow: with OTP"),
    )
    assert parse_text(out).all_projects()[0].bullets[-1].text == "Built the flow: with OTP"


def test_years_nobody_mentioned_are_dropped(client, monkeypatch):
    """Years only stand if the user typed a digit."""
    answers(
        monkeypatch,
        {
            "reply": "ok",
            "changes": [
                {
                    "op": "add_skill_evidence",
                    "target": "Redux",
                    "level": "working",
                    "years": 3,
                }
            ],
        },
    )
    body = say(client, "I used Redux, working level").json()

    redux = next(s for s in parse_text(body["text"]).skill_evidence if s.name == "Redux")
    assert redux.years is None
    assert redux.level == "working"
    assert "years" in body["refused"][0]


def test_years_the_person_gave_are_kept(client, monkeypatch):
    answers(
        monkeypatch,
        {
            "reply": "ok",
            "changes": [
                {"op": "add_skill_evidence", "target": "Redux", "level": "working", "years": 3}
            ],
        },
    )
    body = say(client, "Redux for about 3 years, working level").json()

    redux = next(s for s in parse_text(body["text"]).skill_evidence if s.name == "Redux")
    assert redux.years == 3
    assert body["refused"] == []


# ---------- the proposal has to survive a question ----------


def test_a_question_mid_thread_does_not_lose_the_proposal(client, monkeypatch):
    answers(
        monkeypatch,
        {
            "reply": "Adding it at working level.",
            "changes": [
                {
                    "op": "add_skill_evidence",
                    "target": "RTK Query",
                    "level": "working",
                    "evidence": ["thing"],
                }
            ],
        },
    )
    first = say(client, "I used RTK Query on Thing, working level").json()
    assert first["text"] is not None

    answers(monkeypatch, {"reply": "No, it is not in your skills yet.", "changes": []})
    asked = say(
        client,
        "Do I already have RTK Query?",
        history=[{"role": "you", "text": "I used RTK Query on Thing, working level"}],
    ).json()

    # The browser hands the standing proposal back.
    sent = answers(monkeypatch, {"reply": "Added it.", "changes": []})
    body = client.post(
        "/api/profile/ask",
        json={
            "message": "Yes, add it.",
            "history": [{"role": "you", "text": "I used RTK Query on Thing, working level"}],
            "pending": first["changes"],
        },
    ).json()

    assert "ALREADY PROPOSED" in sent["prompt"]
    assert "RTK Query" in sent["prompt"]
    entry = next(s for s in parse_text(body["text"]).skill_evidence if s.name == "RTK Query")
    assert entry.level == "working"
    assert entry.evidence == ["thing"]


def test_a_correction_replaces_only_the_field_it_names(client, monkeypatch):
    answers(
        monkeypatch,
        {
            "reply": "ok",
            "changes": [
                {
                    "op": "add_skill_evidence",
                    "target": "RTK Query",
                    "level": "working",
                    "evidence": ["thing"],
                    "last_used": "2026-08",
                }
            ],
        },
    )
    first = say(client, "RTK Query on Thing, working, last used August 2026").json()

    answers(
        monkeypatch,
        {
            "reply": "Raised it to advanced.",
            "changes": [
                {"op": "add_skill_evidence", "target": "RTK Query", "level": "advanced"}
            ],
        },
    )
    body = client.post(
        "/api/profile/ask",
        json={"message": "actually advanced", "history": [], "pending": first["changes"]},
    ).json()

    entry = next(s for s in parse_text(body["text"]).skill_evidence if s.name == "RTK Query")
    assert entry.level == "advanced"
    assert entry.evidence == ["thing"] and entry.last_used == "2026-08"


def test_an_entry_with_only_a_name_is_refused(client, monkeypatch):
    answers(
        monkeypatch,
        {"reply": "ok", "changes": [{"op": "add_skill_evidence", "target": "RTK Query"}]},
    )
    body = say(client, "add rtk query").json()

    assert body["text"] is None
    assert "says less than leaving it out" in body["refused"][0]


def test_a_skills_row_nobody_named_says_which_rows_exist(client, monkeypatch):
    answers(
        monkeypatch,
        {"reply": "ok", "changes": [{"op": "add_skill_item", "line": "", "target": "RTK Query"}]},
    )
    body = say(client, "add rtk query to my skills").json()

    assert "no row was named" in body["refused"][0]
    assert "Frontend" in body["refused"][0]


def test_every_turn_is_logged_raw(client, monkeypatch, tmp_path):
    """The model's answer before any guard touches it, for tuning the prompt."""
    log = ask.LOG
    answers(
        monkeypatch,
        {"reply": "ok", "changes": [{"op": "add_skill_evidence", "target": "Jest"}]},
    )
    say(client, "ive used jest")

    import json as _json

    line = _json.loads(log.read_text().splitlines()[0])
    assert line["message"] == "ive used jest"
    # The refused change is still in the log: what it tried matters most.
    assert line["answer"]["changes"][0]["target"] == "Jest"


def test_a_broken_log_does_not_break_ask(client, monkeypatch):
    monkeypatch.setattr(ask, "LOG", pathlib.Path("/nope/nowhere/ask.jsonl"))
    answers(
        monkeypatch,
        {"reply": "ok", "changes": [{"op": "add_skill_evidence", "target": "Redux", "level": "working"}]},
    )
    assert say(client, "redux, working").json()["text"] is not None


def test_an_item_with_no_name_is_refused(client, monkeypatch):
    """The item goes in target. A change that leaves it blank adds nothing."""
    answers(
        monkeypatch,
        {
            "reply": "Added Docker.",
            "changes": [{"op": "add_skill_item", "line": "Backend", "text": "Docker"}],
        },
    )
    body = say(client, "working, shipped with it").json()

    assert body["changes"] == []
    assert "no item was named" in body["refused"][0]


def test_a_date_nobody_gave_is_dropped(client, monkeypatch):
    answers(
        monkeypatch,
        {
            "reply": "ok",
            "changes": [
                {
                    "op": "add_skill_evidence",
                    "target": "Docker",
                    "level": "working",
                    "last_used": "2026-08",
                }
            ],
        },
    )
    body = say(client, "working, shipped with it").json()

    assert "last_used" not in body["text"].split("- name: Docker")[1]
    assert "Dropped the date" in body["refused"][0]


def test_a_date_they_gave_is_kept(client, monkeypatch):
    answers(
        monkeypatch,
        {
            "reply": "ok",
            "changes": [
                {
                    "op": "add_skill_evidence",
                    "target": "Docker",
                    "level": "working",
                    "last_used": "2026-08",
                }
            ],
        },
    )
    body = say(client, "used docker up to august 2026").json()

    assert "  last_used: 2026-08" in body["text"]
    assert body["refused"] == []


# ---------- editing a proposal before saving ----------


def test_a_corrected_level_is_applied(client):
    """The model said working, the person says advanced. No model call."""
    body = client.post(
        "/api/profile/ask/edit",
        json={
            "changes": [
                {"op": "add_skill_evidence", "target": "Tailwind", "level": "advanced"}
            ]
        },
    ).json()

    assert "  level: advanced" in body["text"]
    assert body["refused"] == []


def test_an_edit_still_passes_the_structural_guards(client):
    body = client.post(
        "/api/profile/ask/edit",
        json={"changes": [{"op": "add_skill_evidence", "target": "X", "level": "guru"}]},
    ).json()

    assert body["text"] is None
    assert "not a level" in body["refused"][0]


def test_a_number_the_person_typed_is_kept(client):
    """They edited the field themselves, so nobody invented it."""
    body = client.post(
        "/api/profile/ask/edit",
        json={
            "changes": [
                {"op": "add_skill_evidence", "target": "Tailwind", "level": "advanced",
                 "years": 4, "last_used": "2026-10"}
            ]
        },
    ).json()

    assert "  years: 4" in body["text"]
    assert "  last_used: 2026-10" in body["text"]
    assert body["refused"] == []


# ---------- the two calls ----------


def test_a_question_turn_costs_one_call(client, monkeypatch):
    """No op means nothing to fill in, so the second call is skipped."""
    calls = []

    def fake(prompt, schema, turns=None):
        calls.append(schema)
        return {"op": "ask", "reply": "Which project?", "questions": ["Which project?"]}

    monkeypatch.setattr(ask, "generate_json", fake)
    body = say(client, "i used redux").json()

    assert len(calls) == 1
    assert body["questions"] == ["Which project?"]


def test_the_second_call_only_offers_its_own_fields(client, monkeypatch):
    """A skill call has no project_id; a bullet call has no level."""
    seen = {}

    def fake(prompt, schema, turns=None):
        if "op" in schema["properties"]:
            return {"op": "add_bullet", "reply": "ok"}
        seen["fields"] = set(schema["properties"]["changes"]["items"]["properties"])
        seen["required"] = schema["properties"]["changes"]["items"]["required"]
        return {"changes": []}

    monkeypatch.setattr(ask, "generate_json", fake)
    say(client, "add a bullet to thing")

    assert "level" not in seen["fields"]
    assert "years" not in seen["fields"]
    assert seen["required"] == ["project_id", "text"]


def test_an_op_that_fills_in_nothing_is_reported(client, monkeypatch):
    """An empty changes array is valid JSON and a silent no-op. Say so."""

    def fake(prompt, schema, turns=None):
        if "op" in schema["properties"]:
            return {"op": "add_bullet", "reply": "Adding that."}
        return {"changes": []}

    monkeypatch.setattr(ask, "generate_json", fake)
    body = say(client, "tailwind on thing").json()

    assert body["text"] is None
    assert "could not fill it in" in body["refused"][0]


def test_a_question_that_is_not_a_sentence_is_dropped(client, monkeypatch):
    def fake(prompt, schema, turns=None):
        return {"op": "ask", "reply": "ok", "questions": ["Which project?", "op2"]}

    monkeypatch.setattr(ask, "generate_json", fake)
    body = say(client, "i used redux").json()

    assert body["questions"] == ["Which project?"]


def test_a_date_is_not_permission_to_write_years(client, monkeypatch):
    """"last used 2026-10" has digits in it, and says nothing about duration."""
    answers(
        monkeypatch,
        {
            "reply": "ok",
            "changes": [
                {"op": "add_skill_evidence", "target": "Tailwind",
                 "level": "advanced", "years": 3.5}
            ],
        },
    )
    body = say(client, "tailwind, advanced, last used 2026-10").json()

    entry = next(
        s for s in parse_text(body["text"]).skill_evidence if s.name == "Tailwind"
    )
    assert entry.years is None
    assert entry.level == "advanced"
    assert "Dropped the years" in body["refused"][0]
