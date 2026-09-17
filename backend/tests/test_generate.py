"""
The selector and the guard. Its output is ids, so what matters is a bad one:
missing, blocked, or gated with nothing evidencing it. The model is a dict.
"""

import re
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app import auth, generate, model, render
from app.db import get_session
from app.models import CvSection, GeneratedCv, ParsedJd, RequiredSkill, SelectedBullet
from app.render import render_html
from app.profile_parser import parse_text
from app.profile_template import DEFAULT_TEMPLATE
from app.settings import Settings
from fastapi import HTTPException
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


@pytest.fixture(autouse=True)
def no_browser(monkeypatch):
    """
    The fill loop measures a real page. Left alone it would launch Chromium in
    every test in this file and top up selections the guard tests are asserting
    on, so by default the page reports itself full and the loop does nothing.
    Tests for the loop itself override this with fill_to().
    """
    monkeypatch.setattr(generate, "measurer", lambda: _measures(lambda html: 1.0))


@contextmanager
def _measures(fn):
    yield fn


def fill_to(monkeypatch, heights):
    """A measurer that walks a scripted list of page heights."""
    seen = iter(heights)
    monkeypatch.setattr(
        generate, "measurer", lambda: _measures(lambda html: next(seen, heights[-1]))
    )


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
    assert "Company Name" in html and "WORK EXPERIENCE" in html
    assert html.index("Company Name") < html.index("Project Name")
    assert html.index("Side Project") > html.index("PROJECTS")


def test_every_link_on_the_page_is_clickable_and_absolute():
    from app.render import render_html
    from app.models import GeneratedCv

    profile = parse_text(DEFAULT_TEMPLATE)
    plain = dict(CV["sections"][0], project_id="second-project", project_name="Second Project")
    html = render_html(
        profile, GeneratedCv.model_validate({**CV, "sections": [*CV["sections"], plain]})
    )

    # A PDF reader reads a scheme-less href as a file path.
    hrefs = re.findall(r'href="([^"]+)"', html)
    assert hrefs, "the header has links in it, so the page should have anchors"
    assert all(re.match(r"^(https?|mailto|tel):", href) for href in hrefs), hrefs

    assert 'href="mailto:you@example.com"' in html
    assert 'href="https://github.com/you"' in html
    assert "Stack Overflow" in html
    assert '<a href="https://product.example.com">Project Name</a>' in html
    assert '<span class="name">Second Project' in html


def test_certifications_never_reach_the_page():
    """
    They are in the profile so the fit check knows the skills are there. They
    have never been on this CV, earned or otherwise.
    """
    from app.render import render_html
    from app.models import GeneratedCv

    profile = parse_text(DEFAULT_TEMPLATE)
    assert profile.certifications, "the fixture should have some to leave out"
    html = render_html(profile, GeneratedCv.model_validate(CV))
    assert "CERTIFICATIONS" not in html
    assert "Certification Name" not in html
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

    monkeypatch.setattr(generate, "to_pdf", lambda html: (b"%PDF-1.4 rebuilt", 1))
    assert client.post("/api/reexport", json={"application_id": application_id}).status_code == 200

    assert client.get(f"/api/applications/{application_id}/pdf").content == b"%PDF-1.4 rebuilt"
    after = client.get(f"/api/applications/{application_id}").json()
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


# ---------- the layout, against docs/cv/ShehzarAurangzeb.html ----------


def test_the_fonts_survive_autoescaping():
    """
    Jinja escaped the quotes in format('truetype') and Chromium silently dropped
    every @font-face, so the page printed in Helvetica while claiming Inter. The
    escaping is invisible in the markup; only the rendered PDF showed it.
    """
    from app.render import render_html
    from app.models import GeneratedCv

    html = render_html(parse_text(DEFAULT_TEMPLATE), GeneratedCv.model_validate(CV))
    assert html.count("@font-face") == 4
    assert "format('truetype')" in html
    assert "&#39;" not in html


def test_a_project_leads_in_with_its_first_bullet_on_the_same_line():
    """
    The source document runs the project name straight into its first bullet.
    It is what makes the page fit, so it is the one structural rule here.
    """
    from app.render import render_html
    from app.models import GeneratedCv

    cv = GeneratedCv.model_validate(
        {
            **CV,
            "sections": [
                {
                    **CV["sections"][0],
                    "bullets": [
                        {"id": "a", "source_id": "a", "text": "First one."},
                        {"id": "b", "source_id": "b", "text": "Second one."},
                    ],
                }
            ],
        }
    )
    html = render_html(parse_text(DEFAULT_TEMPLATE), cv)
    assert "(A product)</span> · First one." in html
    assert "<li>Second one.</li>" in html
    assert "<li>First one.</li>" not in html


def test_an_unnamed_project_prints_bullets_with_no_lead_in():
    """Small client work in the source CV has no bold heading of its own."""
    from app.render import render_html
    from app.models import GeneratedCv

    cv = GeneratedCv.model_validate(
        {**CV, "sections": [{**CV["sections"][0], "named": False}]}
    )
    html = render_html(parse_text(DEFAULT_TEMPLATE), cv)
    assert "Project Name" not in html
    assert "Built a thing." in html


def test_dates_are_printed_for_a_person_not_a_sorter():
    from app.render import _month

    assert _month("2024-11") == "Nov 2024"
    assert _month("2026-6") == "Jun 2026"
    assert _month("present") == "Present"
    # Anything that is not a month passes through rather than being mangled.
    assert _month("2024") == "2024"
    assert _month("") == ""


# ---------- filling the page ----------
#
# The complaint these answer: four bullets came back, the page was half empty,
# and nothing noticed.


def test_a_short_page_is_topped_up_until_it_is_full(client, monkeypatch):
    save_profile(client)
    fill_to(monkeypatch, [0.5, 0.7, 0.9, 0.95])
    body = run(client, monkeypatch, PICKED)

    printed = [b["id"] for s in body["cv"]["sections"] for b in s["bullets"]]
    assert len(printed) > 1, "the selector picked one bullet and the page was half empty"
    assert "project-name-perf" in printed, "what the selector chose stays chosen"
    assert any("fill the page" in f["message"] for f in body["flags"])


def test_a_page_that_is_already_full_is_left_alone(client, monkeypatch):
    save_profile(client)
    fill_to(monkeypatch, [0.95])
    body = run(client, monkeypatch, PICKED)
    assert [b["id"] for s in body["cv"]["sections"] for b in s["bullets"]] == ["project-name-perf"]
    assert not any("fill the page" in f["message"] for f in body["flags"])


def test_a_top_up_that_would_spill_onto_a_second_page_is_taken_back(client, monkeypatch):
    save_profile(client)
    fill_to(monkeypatch, [0.5, 1.6])
    body = run(client, monkeypatch, PICKED)
    assert [b["id"] for s in body["cv"]["sections"] for b in s["bullets"]] == ["project-name-perf"]


def test_a_blocked_bullet_is_never_used_to_fill(client, monkeypatch):
    save_profile(client)
    fill_to(monkeypatch, [0.1] * 20)
    body = run(client, monkeypatch, PICKED)
    printed = [b["id"] for s in body["cv"]["sections"] for b in s["bullets"]]
    # project-name-migration is status: blocked in the shipped template.
    assert "project-name-migration" not in printed


def test_the_caps_still_hold_while_filling(client, monkeypatch):
    save_profile(client)
    fill_to(monkeypatch, [0.1] * 40)
    body = run(client, monkeypatch, PICKED)
    profile = parse_text(DEFAULT_TEMPLATE)
    assert len(body["cv"]["sections"]) <= profile.rules.max_projects
    for section in body["cv"]["sections"]:
        assert len(section["bullets"]) <= profile.rules.max_bullets_per_project


def test_nothing_left_to_add_says_so_rather_than_silently_shipping_short(client, monkeypatch):
    save_profile(client, BANNED.replace("Spearheaded the rewrite.", "Built the rewrite."))
    fill_to(monkeypatch, [0.3] * 10)
    body = run(
        client,
        monkeypatch,
        {"title_id": "", "sections": [{"project_id": "p", "bullet_ids": ["p-one"]}]},
    )
    assert any("nothing unused left to add" in f["message"] for f in body["flags"])


def test_no_browser_does_not_stop_a_cv_being_generated(client, monkeypatch):
    save_profile(client)

    def broken():
        raise RuntimeError("Chromium is not installed")

    monkeypatch.setattr(generate, "measurer", broken)
    body = run(client, monkeypatch, PICKED)
    assert body["cv"]["sections"], "an unmeasurable page is still a page"
    assert any("Could not measure" in f["message"] for f in body["flags"])


# ---------- coverage: what the page backs ----------
#
# The substring scan this replaced backed 1 of 6 requirements, because only one
# appeared word for word. Meaning is the model's job, honesty is this code's.


def _jd(*names: str) -> ParsedJd:
    return ParsedJd(required_skills=[RequiredSkill(name=n, importance=3) for n in names])


def _sections(**by_project: list[str]) -> list[CvSection]:
    return [
        CvSection(
            project_id=project,
            project_name=project,
            bullets=[
                SelectedBullet(id=i, text=i, source_id=i) for i in ids
            ],
        )
        for project, ids in by_project.items()
    ]


def test_coverage_credits_a_bullet_that_never_says_the_words():
    answer = {"coverage": [{"skill": "Mobile App Development", "bullet_ids": ["sp-app"]}]}
    result = generate._coverage(_jd("Mobile App Development"), answer, _sections(sp=["sp-app"]))
    assert [(c.skill, c.bullet_ids) for c in result] == [
        ("Mobile App Development", ["sp-app"])
    ]
    assert result[0].bullet_ids  # evidenced


def test_coverage_drops_a_bullet_that_did_not_print():
    """The page-fill loop and a deselect both change what is on the page."""
    answer = {"coverage": [{"skill": "TypeScript", "bullet_ids": ["gone", "here"]}]}
    result = generate._coverage(_jd("TypeScript"), answer, _sections(sp=["here"]))
    assert result[0].bullet_ids == ["here"]


def test_coverage_reports_every_requirement_even_the_unbacked_ones():
    """An empty list is the answer that matters: the posting wants what you lack."""
    answer = {"coverage": [{"skill": "React Native", "bullet_ids": ["sp-app"]}]}
    result = generate._coverage(
        _jd("React Native", "Xcode"), answer, _sections(sp=["sp-app"])
    )
    assert [c.skill for c in result] == ["React Native", "Xcode"]
    assert result[1].bullet_ids == []


def test_coverage_ignores_a_skill_the_posting_never_asked_for():
    answer = {"coverage": [{"skill": "Fortran", "bullet_ids": ["sp-app"]}]}
    result = generate._coverage(_jd("TypeScript"), answer, _sections(sp=["sp-app"]))
    assert [c.skill for c in result] == ["TypeScript"]


def test_coverage_matches_the_skill_name_case_and_space_insensitively():
    answer = {"coverage": [{"skill": " restful apis ", "bullet_ids": ["sp-app"]}]}
    result = generate._coverage(_jd("RESTful APIs"), answer, _sections(sp=["sp-app"]))
    assert result[0].bullet_ids == ["sp-app"]


# ---------- preview ----------
#
# The preview used to be separate markup approximating the layout, and had
# drifted from cv.html unnoticed. These pin that both come off one template.


def test_preview_is_the_same_html_the_pdf_prints_from(client):
    save_profile(client)
    html = client.post("/api/preview", json={"cv": CV}).text

    source = client.get("/api/profile/source").json()["text"]
    assert html == render_html(parse_text(source), GeneratedCv.model_validate(CV))


def test_preview_needs_a_profile():
    from app.main import app

    with TestClient(app) as fresh:
        fresh.post("/api/auth/login", json={"password": PASSWORD})
        assert fresh.post("/api/preview", json={"cv": CV}).status_code in (404, 401)


# ---------- labels that name their own links ----------


def test_a_label_naming_its_links_gets_them_hyperlinked():
    """"live on App Store + Play Store" links both phrases, not the project name."""
    from app.models import Link

    links = [
        Link(label="App Store", url="apps.apple.com/ca/app/x/id1"),
        Link(label="Play Store", url="play.google.com/store/apps/details?id=y"),
    ]
    html, used = render._linkify("React Native application, live on App Store + Play Store", links)
    assert used
    assert '<a href="https://apps.apple.com/ca/app/x/id1">App Store</a>' in html
    assert '<a href="https://play.google.com/store/apps/details?id=y">Play Store</a>' in html


def test_a_label_that_names_nothing_leaves_the_links_for_the_name():
    from app.models import Link

    html, used = render._linkify("A tailoring app", [Link(label="Repo", url="github.com/x")])
    assert not used and html == "A tailoring app"


def test_linkify_escapes_the_label_it_did_not_link():
    from app.models import Link

    html, _ = render._linkify("Tools & <toys>", [Link(label="Tools", url="x.com")])
    assert "&amp;" in html and "&lt;toys&gt;" in html


# ---------- when the model answers badly ----------
#
# Each is a 502 with a sentence, not a traceback and not a half-built CV. The
# selector cannot be made to answer well, only stopped from doing damage.


def _reply(monkeypatch, payload):
    """A Gemini response envelope holding whatever text is given."""

    class Fake:
        status_code = 200

        @staticmethod
        def json():
            return payload

    monkeypatch.setattr(model, "get_settings", lambda: Settings(secret_key="t", gemini_api_key="k"))
    monkeypatch.setattr(model.httpx, "post", lambda *a, **k: Fake())


def _wrapped(text: str) -> dict:
    return {"candidates": [{"content": {"parts": [{"text": text}]}}]}


def test_prose_where_json_was_asked_for_is_a_502(monkeypatch):
    _reply(monkeypatch, _wrapped("Sure! Here is your CV: ..."))
    with pytest.raises(HTTPException) as caught:
        model.generate_json("p", generate.SCHEMA)
    assert caught.value.status_code == 502 and "unreadable" in caught.value.detail


def test_truncated_json_is_a_502(monkeypatch):
    _reply(monkeypatch, _wrapped('{"title_id": "frontend", "sections": ['))
    with pytest.raises(HTTPException) as caught:
        model.generate_json("p", generate.SCHEMA)
    assert caught.value.status_code == 502


def test_a_blocked_or_empty_answer_says_so(monkeypatch):
    """No candidates is a safety block, not a parse problem, and reads that way."""
    _reply(monkeypatch, {"candidates": []})
    with pytest.raises(HTTPException) as caught:
        model.generate_json("p", generate.SCHEMA)
    assert caught.value.status_code == 502 and "blocked" in caught.value.detail


def test_a_shape_we_did_not_expect_is_a_502_not_a_keyerror(monkeypatch):
    _reply(monkeypatch, {"candidates": [{"content": {}}]})
    with pytest.raises(HTTPException) as caught:
        model.generate_json("p", generate.SCHEMA)
    assert caught.value.status_code == 502
