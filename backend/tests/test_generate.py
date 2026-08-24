"""
The selector and the guard.

The selector's output is ids, so the tests that matter are about what happens to
an id: one that does not exist, one that points at a blocked bullet, one that
brings a gated skill onto the page with nothing evidencing it. Nothing here
reaches the network; the model is a dict.
"""

import re

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app import auth, generate
from app.db import get_session
from app.profile_parser import parse_text
from app.profile_template import DEFAULT_TEMPLATE
from app.settings import Settings
from app.tables import ProfileSource

PASSWORD = "correct horse battery staple"

JD = """Front-End Developer, Montreal. Build customer-facing React interfaces in
TypeScript, contribute to a shared component library, work with designers on
accessible layouts. Required: 3+ years React and TypeScript."""

PICKED = {
    "title_id": "frontend",
    "sections": [{"project_id": "project-name", "bullet_ids": ["project-name-perf"]}],
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
    sent = {}

    def fake(prompt, schema):
        sent["prompt"] = prompt
        return payload

    monkeypatch.setattr(generate, "generate_json", fake)
    return sent


def run(client, monkeypatch, payload, **body):
    answers(monkeypatch, payload)
    return client.post("/api/generate", json={"jd_text": JD, **body}).json()


# ---------- the route ----------


def test_it_needs_a_session(client):
    client.post("/api/auth/logout")
    assert client.post("/api/generate", json={"jd_text": JD}).status_code == 401


def test_no_profile_means_nothing_to_select_from(client):
    assert client.post("/api/generate", json={"jd_text": JD}).status_code == 404


def test_a_profile_of_only_blocked_bullets_says_so(client):
    save_profile(
        client,
        "# Identity\nname: N\n\n# Experience\n## Co\n### P\nbullets:\n"
        "  - id: p-one\n    status: blocked\n    text: x\n",
    )
    response = client.post("/api/generate", json={"jd_text": JD})
    assert response.status_code == 422
    assert "blocked" in response.json()["detail"]


# ---------- assembly ----------


def test_the_text_comes_from_the_profile_not_the_model(client, monkeypatch):
    save_profile(client)
    body = run(client, monkeypatch, PICKED)

    profile = parse_text(DEFAULT_TEMPLATE)
    bullet = profile.experience[0].projects[0].bullets[0]
    printed = body["cv"]["sections"][0]["bullets"][0]
    assert printed["text"] == bullet.text
    assert printed["source_id"] == bullet.id and printed["rephrased"] is False
    assert body["cv"]["title"] == next(t.text for t in profile.titles if t.id == "frontend")
    assert body["cv"]["summary"] == next(s.text for s in profile.summaries if s.id == "frontend")


def test_the_pool_never_contains_a_blocked_bullet(client, monkeypatch):
    save_profile(client)
    sent = answers(monkeypatch, PICKED)
    client.post("/api/generate", json={"jd_text": JD})

    profile = parse_text(DEFAULT_TEMPLATE)
    blocked = next(
        b for p in profile.all_projects() for b in p.bullets if b.status == "blocked"
    )
    assert blocked.id not in sent["prompt"]


def test_an_unknown_title_falls_back_and_says_so(client, monkeypatch):
    save_profile(client)
    body = run(client, monkeypatch, {**PICKED, "title_id": "ghost"})
    assert body["cv"]["title"]
    assert any("ghost" in flag["message"] for flag in body["flags"])


def test_the_chosen_framing_wins_over_the_model(client, monkeypatch):
    save_profile(client)
    body = run(client, monkeypatch, PICKED, title_variant="fullstack")
    profile = parse_text(DEFAULT_TEMPLATE)
    assert body["cv"]["title"] == next(t.text for t in profile.titles if t.id == "fullstack")


# ---------- the guard ----------


def test_an_id_that_does_not_exist_is_blocked(client, monkeypatch):
    save_profile(client)
    body = run(
        client,
        monkeypatch,
        {"title_id": "frontend", "sections": [{"project_id": "project-name", "bullet_ids": ["invented"]}]},
    )
    assert any(f["type"] == "block" and "invented" in f["message"] for f in body["flags"])
    assert body["cv"]["sections"] == []


def test_a_project_that_does_not_exist_is_blocked(client, monkeypatch):
    save_profile(client)
    body = run(
        client,
        monkeypatch,
        {"title_id": "frontend", "sections": [{"project_id": "ghost", "bullet_ids": ["x"]}]},
    )
    assert any(f["type"] == "block" and "ghost" in f["message"] for f in body["flags"])


def test_a_blocked_bullet_selected_anyway_never_prints(client, monkeypatch):
    """It is kept out of the pool. Reaching here means the id came from nowhere."""
    save_profile(client)
    body = run(
        client,
        monkeypatch,
        {
            "title_id": "frontend",
            "sections": [
                {"project_id": "project-name", "bullet_ids": ["project-name-migration"]}
            ],
        },
    )
    assert any(f["type"] == "block" and "blocked" in f["message"] for f in body["flags"])
    assert body["cv"]["sections"] == []


def test_the_rules_caps_are_enforced_after_the_answer(client, monkeypatch):
    """A model that ignores "at most 3" must not put four on the page."""
    save_profile(client)
    body = run(
        client,
        monkeypatch,
        {
            "title_id": "frontend",
            "sections": [
                {
                    "project_id": "project-name",
                    "bullet_ids": ["project-name-perf", "project-name-ci"] * 4,
                }
            ],
        },
    )
    assert len(body["cv"]["sections"][0]["bullets"]) == 3


BANNED = """# Identity
name: N

# Skills
- line: Frontend
  items: [React]

# Experience
## Co
### P
claim_boundary:
  cannot_claim:
    - The deploy
bullets:
  - id: p-one
    text: Spearheaded the rewrite.

# Rules
banned_words:
  - spearheaded
banned_chars:
  - U+2014
"""


def test_a_banned_word_that_reaches_the_page_is_blocked(client, monkeypatch):
    save_profile(client, BANNED)
    body = run(
        client,
        monkeypatch,
        {"title_id": "", "sections": [{"project_id": "p", "bullet_ids": ["p-one"]}]},
    )
    assert any(f["type"] == "block" and "spearheaded" in f["message"] for f in body["flags"])


def test_a_banned_character_is_matched_through_its_codepoint(client, monkeypatch):
    """Rules writes U+2014 so the profile itself contains no em dash."""
    save_profile(client, BANNED.replace("Spearheaded the", "Did the —"))
    body = run(
        client,
        monkeypatch,
        {"title_id": "", "sections": [{"project_id": "p", "bullet_ids": ["p-one"]}]},
    )
    assert any("banned character" in f["message"] for f in body["flags"])


QUALIFIED = """# Identity
name: N

# Experience
## Co
### P
claim_boundary:
  cannot_claim:
    - The deploy
  required_qualifiers:
    - The figure is estimated rather than measured
bullets:
  - id: p-one
    text: Cut load time by 40 percent.
  - id: p-two
    text: Cut load time by an estimated 40 percent.
"""


def test_a_missing_required_qualifier_is_a_warning(client, monkeypatch):
    save_profile(client, QUALIFIED)
    body = run(
        client,
        monkeypatch,
        {"title_id": "", "sections": [{"project_id": "p", "bullet_ids": ["p-one"]}]},
    )
    assert any(f["type"] == "warn" and "qualifier" in f["message"] for f in body["flags"])


def test_the_qualifier_travelling_with_the_claim_clears_it(client, monkeypatch):
    save_profile(client, QUALIFIED)
    body = run(
        client,
        monkeypatch,
        {"title_id": "", "sections": [{"project_id": "p", "bullet_ids": ["p-two"]}]},
    )
    assert not any("qualifier" in f["message"] for f in body["flags"])


# ---------- the skills line ----------


def test_a_gated_skill_stays_off_the_page_without_its_project(client, monkeypatch):
    save_profile(client)
    body = run(client, monkeypatch, PICKED)
    printed = [item for line in body["cv"]["skills_lines"] for item in line["items"]]
    assert "AWS" not in printed
    assert "React" in printed


def test_a_gated_skill_prints_once_its_project_is_selected(client, monkeypatch):
    save_profile(client)
    body = run(
        client,
        monkeypatch,
        {
            "title_id": "frontend",
            "sections": [{"project_id": "side-project", "bullet_ids": ["side-project-infra"]}],
        },
    )
    printed = [item for line in body["cv"]["skills_lines"] for item in line["items"]]
    assert "AWS" in printed


def test_never_standalone_is_dropped_when_it_would_be_alone():
    profile = parse_text(
        "# Identity\nname: N\n\n# Skills\n- line: Frontend\n  items: [RxJS]\n"
        "  never_standalone: [RxJS]\n"
    )
    assert generate._skills(profile, set()) == []


def test_nothing_selected_is_a_block_not_an_empty_page(client, monkeypatch):
    save_profile(client)
    body = run(client, monkeypatch, {"title_id": "frontend", "sections": []})
    assert any(f["type"] == "block" and "no CV" in f["message"] for f in body["flags"])


# ---------- export ----------


def stub_pdf(monkeypatch, pages=1):
    """No browser in the suite. Chromium is exercised by hand, not by pytest."""
    monkeypatch.setattr(generate, "to_pdf", lambda html: (b"%PDF-1.4 " + html[:20].encode(), pages))


def make_application(client):
    return client.post(
        "/api/applications",
        json={
            "company": "Air Canada",
            "role": "Front End Developer",
            "jd_text": JD,
            "fit_score": 8,
        },
    ).json()["id"]


CV = {
    "title": "Front-End Engineer",
    "summary": "Two sentences.",
    "skills_lines": [{"line": "Frontend", "items": ["React"]}],
    "sections": [
        {
            "project_id": "project-name",
            "project_name": "Project Name",
            "label": "A product",
            "stack": ["React"],
            "bullets": [
                {"id": "project-name-perf", "text": "Built a thing.", "source_id": "project-name-perf", "rephrased": False}
            ],
        }
    ],
}


def test_export_needs_a_row_to_attach_to(client, monkeypatch):
    save_profile(client)
    stub_pdf(monkeypatch)
    response = client.post("/api/export", json={"application_id": 999, "cv": CV})
    assert response.status_code == 404


def test_export_attaches_the_pdf_and_records_what_was_sent(client, monkeypatch):
    save_profile(client)
    stub_pdf(monkeypatch)
    application_id = make_application(client)

    body = client.post("/api/export", json={"application_id": application_id, "cv": CV}).json()
    assert body["page_count"] == 1
    assert body["filename"].startswith("YourName_AirCanada_FrontEndDeveloper_")
    assert body["filename"].endswith(".pdf")

    row = client.get(f"/api/applications/{application_id}").json()
    assert row["has_pdf"] is True
    assert row["title_variant"] == "Front-End Engineer"
    assert row["summary_text"] == "Two sentences."
    assert row["selected_bullet_ids"] == ["project-name-perf"]
    assert row["selected_bullets"][0]["project_name"] == "Project Name"

    served = client.get(f"/api/applications/{application_id}/pdf")
    assert served.status_code == 200 and served.content.startswith(b"%PDF")


def test_the_record_is_what_was_on_screen_not_what_the_selector_said(client, monkeypatch):
    """Deselecting a bullet has to reach the archive, or the archive is fiction."""
    save_profile(client)
    stub_pdf(monkeypatch)
    application_id = make_application(client)
    trimmed = {**CV, "sections": [{**CV["sections"][0], "bullets": []}]}

    client.post("/api/export", json={"application_id": application_id, "cv": trimmed})
    row = client.get(f"/api/applications/{application_id}").json()
    assert row["selected_bullet_ids"] == []


# ---------- the rendered page ----------


def test_the_html_puts_projects_back_under_their_employer():
    from app.render import render_html
    from app.models import GeneratedCv

    profile = parse_text(DEFAULT_TEMPLATE)
    cv = GeneratedCv.model_validate(
        {
            **CV,
            "sections": [
                CV["sections"][0],
                {
                    "project_id": "side-project",
                    "project_name": "Side Project",
                    "label": "Mine",
                    "stack": ["Next.js"],
                    "bullets": [
                        {"id": "side-project-infra", "text": "Built it.", "source_id": "side-project-infra"}
                    ],
                },
            ],
        }
    )
    html = render_html(profile, cv)
    # The selector answers in project ids and knows nothing about employers.
    assert "Company Name" in html and "Work experience" in html.replace("</h2>", "")
    assert html.index("Company Name") < html.index("Project Name")
    # Standalone work is its own section, not filed under a company.
    assert html.index("Side Project") > html.index("Projects")


def test_every_link_on_the_page_is_clickable_and_absolute():
    from app.render import render_html
    from app.models import GeneratedCv

    profile = parse_text(DEFAULT_TEMPLATE)
    plain = dict(CV["sections"][0], project_id="second-project", project_name="Second Project")
    html = render_html(
        profile, GeneratedCv.model_validate({**CV, "sections": [*CV["sections"], plain]})
    )

    # Profiles are written "github.com/you". A href with no scheme is read as a
    # file path by a PDF reader, so it must not survive to the page.
    hrefs = re.findall(r'href="([^"]+)"', html)
    assert hrefs, "the header has links in it, so the page should have anchors"
    assert all(re.match(r"^(https?|mailto|tel):", href) for href in hrefs), hrefs

    assert 'href="mailto:you@example.com"' in html
    assert 'href="https://github.com/you"' in html
    # Written in Identity as extra header content, and once dropped on the floor.
    assert "Stack Overflow" in html
    # A project with links has its name linked; one without stays plain text.
    assert 'class="name linked" href="https://product.example.com"' in html
    assert '<span class="name">Second Project</span>' in html


def test_an_in_progress_certification_never_prints():
    from app.render import render_html
    from app.models import GeneratedCv

    profile = parse_text(DEFAULT_TEMPLATE)
    html = render_html(profile, GeneratedCv.model_validate(CV))
    assert "Certification Name" in html
    assert "A Course You Are Halfway Through" not in html


def test_the_filename_says_who_where_and_when():
    from app.render import filename
    from datetime import date

    assert (
        filename("Shehzar Aurangzeb Abbasi", "Air Canada", "Front-End Developer", date(2026, 8, 23))
        == "ShehzarAurangzebAbbasi_AirCanada_FrontEndDeveloper_2026-08-23.pdf"
    )


# ---------- TEMPORARY: re-export. Delete with the route. ----------


def test_reexport_rebuilds_the_pdf_without_touching_the_record(client, monkeypatch):
    save_profile(client)
    stub_pdf(monkeypatch)
    application_id = make_application(client)
    client.post("/api/export", json={"application_id": application_id, "cv": CV})
    before = client.get(f"/api/applications/{application_id}").json()

    # A template fix lands, and the stored bytes are the only copy of the old one.
    monkeypatch.setattr(generate, "to_pdf", lambda html: (b"%PDF-1.4 rebuilt", 1))
    assert client.post("/api/reexport", json={"application_id": application_id}).status_code == 200

    assert client.get(f"/api/applications/{application_id}/pdf").content == b"%PDF-1.4 rebuilt"
    after = client.get(f"/api/applications/{application_id}").json()
    # What was sent is history. Re-rendering must not rewrite it.
    for field in ("title_variant", "summary_text", "selected_bullet_ids", "selected_bullets"):
        assert after[field] == before[field], field


def test_reexport_uses_the_text_that_was_sent_not_the_profile_as_it_is_now(client, monkeypatch):
    save_profile(client)
    stub_pdf(monkeypatch)
    application_id = make_application(client)
    edited = {
        **CV,
        "sections": [{**CV["sections"][0], "bullets": [{**CV["sections"][0]["bullets"][0], "text": "What they read."}]}],
    }
    client.post("/api/export", json={"application_id": application_id, "cv": edited})

    printed = {}

    def capture(html):
        printed["html"] = html
        return b"%PDF-1.4 x", 1

    monkeypatch.setattr(generate, "to_pdf", capture)
    client.post("/api/reexport", json={"application_id": application_id})
    assert "What they read." in printed["html"]


def test_reexport_needs_something_to_rebuild(client, monkeypatch):
    save_profile(client)
    application_id = make_application(client)
    response = client.post("/api/reexport", json={"application_id": application_id})
    assert response.status_code == 422 and "nothing to rebuild" in response.json()["detail"]
    assert client.post("/api/reexport", json={"application_id": 999}).status_code == 404
