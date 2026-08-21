"""
The template and the briefing are environment-overridable so they can be
reworded without a deploy of code. The branch worth pinning is the one that
decides where the template lands inside the briefing.
"""

import pytest

from app import profile_template
from app.profile_parser import parse_text
from app.settings import Settings


@pytest.fixture(autouse=True)
def _no_env_override(monkeypatch):
    monkeypatch.setattr(profile_template, "get_settings", lambda: Settings(secret_key="test"))


def override(monkeypatch, **fields):
    monkeypatch.setattr(
        profile_template, "get_settings", lambda: Settings(secret_key="test", **fields)
    )


def test_the_shipped_template_actually_parses():
    """It did not, once: four column-0 comments were read as section breaks."""
    profile = parse_text(profile_template.template())
    assert len(profile.titles) == 2
    assert sum(len(p.bullets) for e in profile.experience for p in e.projects) == 2
    assert profile.experience[0].projects[0].claim_boundary.cannot_claim


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
