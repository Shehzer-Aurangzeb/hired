import re
from pathlib import Path
from urllib.parse import quote

import pytest

from app import profile_template
from app.profile_parser import parse_text, validate_text
from app.settings import Settings

DOCS = Path(__file__).parents[2] / "docs"
FRONTEND = Path(__file__).parents[2] / "frontend" / "src" / "app" / "core" / "claude-draft.ts"


@pytest.fixture(autouse=True)
def _no_env_override(monkeypatch):
    monkeypatch.setattr(profile_template, "get_settings", lambda: Settings(secret_key="test"))


def override(monkeypatch, **fields):
    monkeypatch.setattr(
        profile_template, "get_settings", lambda: Settings(secret_key="test", **fields)
    )


# ---------- the copy in the module ----------


def test_the_constants_match_their_editable_source():
    """The module's copies must not drift from the docs/ sources."""
    template = (DOCS / "master_template.md").read_text(encoding="utf-8")
    briefing = (DOCS / "master_interview_prompt.md").read_text(encoding="utf-8")
    assert profile_template.DEFAULT_TEMPLATE.rstrip("\n") == template.rstrip("\n")
    assert profile_template.DEFAULT_BRIEFING.rstrip("\n") == briefing.rstrip("\n").replace(
        "{{TEMPLATE}}", "{template}"
    )


def test_the_briefing_holds_one_placeholder_and_no_other_braces():
    assert re.findall(r"\{[^}]*\}", profile_template.DEFAULT_BRIEFING) == ["{template}"]
    assert "{" not in profile_template.DEFAULT_TEMPLATE
    assert "}" not in profile_template.DEFAULT_TEMPLATE


# ---------- the template itself ----------


def test_the_shipped_template_actually_parses():
    profile = parse_text(profile_template.template())
    assert len(profile.titles) == 2
    projects = profile.all_projects()
    assert len(projects) == 4
    assert sum(len(p.bullets) for p in projects) == 6
    assert all(p.claim_boundary.cannot_claim for p in projects)


def test_the_shipped_template_validates_silently():
    result = validate_text(profile_template.template())
    assert result.ok and result.warnings == []
    assert result.summary.projects_total == 4
    assert result.summary.gaps == 3 and result.summary.unverified == 1


def test_the_shipped_template_demonstrates_every_field():
    profile = parse_text(profile_template.template())

    assert profile.meta.schema_version == 1 and profile.meta.updated
    assert all(t.use_when for t in profile.titles)
    assert profile.identity.links and profile.identity.authorization

    react, aws = profile.skill_evidence
    assert (react.years, react.level, react.context) == (4.0, "advanced", "professional")
    assert react.evidence and aws.gated

    company = profile.experience[0]
    assert company.employment_type and company.context and company.disclosure
    assert company.previous_roles[0].role

    project = company.projects[0]
    assert project.my_role and project.status and project.domain
    assert project.start and project.end and project.unverified
    assert project.stack and project.links and project.disclosure
    assert project.claim_boundary.required_qualifiers

    first, _, blocked = project.bullets
    assert first.short and first.metric and first.metric.source == "measured"
    assert first.metric.value and first.metric.method
    assert blocked.status == "blocked" and blocked.blocked_reason

    loose = profile.projects[0]
    assert loose.why_built and loose.id == "side-project"

    school = profile.education[0]
    assert school.gpa and school.coursework and school.priority == 2
    assert school.notes and school.links

    assert [c.status for c in profile.certifications] == ["earned", "in_progress"]
    assert profile.certifications[0].expires
    assert profile.publications[0].type == "talk"
    assert profile.awards[0].note

    english, french = profile.languages
    assert (english.level, english.note) == ("native", "")
    assert french.note

    availability = profile.availability
    assert availability.work_modes and availability.locations
    assert availability.earliest_start and availability.notice_period
    assert availability.employment_types and availability.compensation
    assert availability.travel_ok and availability.deal_breakers

    assert [g.skill for g in profile.gaps] == ["Kubernetes", "Angular", "React Native"]
    assert all(g.status and g.bridge and g.blocks for g in profile.gaps)

    rules = profile.rules
    assert rules.banned_words and rules.banned_chars and rules.preferred_phrasing
    assert (rules.max_bullets_per_project, rules.max_projects, rules.page_limit) == (3, 5, 1)

    assert any(row.gated for row in profile.skills)
    assert any(row.never_standalone for row in profile.skills)


# ---------- the prompt ----------


def test_prompt_carries_the_template():
    prompt = profile_template.claude_prompt()
    assert profile_template.template().strip() in prompt
    assert "{template}" not in prompt


def test_placeholder_decides_where_the_template_lands(monkeypatch):
    override(monkeypatch, profile_template="TEMPLATE", claude_briefing="before {template} after")
    assert profile_template.claude_prompt() == "before TEMPLATE after"


def test_a_briefing_without_the_placeholder_still_gets_the_template(monkeypatch):
    """A reworded briefing must not be able to silently drop the file it is about."""
    override(monkeypatch, profile_template="TEMPLATE", claude_briefing="no placeholder here")
    assert profile_template.claude_prompt() == "no placeholder here\n\nTEMPLATE"


# ---------- and why it cannot travel in a URL ----------


def test_the_prompt_is_far_too_large_for_a_query_string():
    """Why the button copies the prompt instead of linking to it."""
    assert len(quote(profile_template.claude_prompt())) > 40_000


def test_the_bootstrap_url_stays_under_2000_characters():
    """Longer request lines get refused or truncated along the way."""
    bootstrap = "".join(re.findall(r"'([^']*)'", _assignment("BOOTSTRAP")))
    assert bootstrap
    assert len(f"https://claude.ai/new?q={quote(bootstrap)}") < 2000


def test_the_frontend_never_puts_the_prompt_in_the_url():
    url = _assignment("CLAUDE_URL")
    assert "BOOTSTRAP" in url and "prompt" not in url


def _assignment(name: str) -> str:
    source = FRONTEND.read_text(encoding="utf-8")
    return source.split(f"export const {name} =", 1)[1].split(";", 1)[0]
