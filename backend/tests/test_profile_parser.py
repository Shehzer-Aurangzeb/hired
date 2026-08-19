from pathlib import Path

import pytest
from pydantic import ValidationError

from app.profile_parser import parse

FIXTURE = Path(__file__).parent / "fixtures" / "master.md"


@pytest.fixture(scope="module")
def profile():
    return parse(FIXTURE)


def test_identity(profile):
    assert profile.identity.name == "Test Person"
    assert profile.identity.email == "test@example.com"
    assert profile.identity.phone == "+1 514 000 0000"


def test_titles_summaries_skills(profile):
    assert [t.id for t in profile.titles] == ["fullstack", "frontend"]
    assert profile.summaries[0].max_chars == 520
    assert "TypeScript" in profile.summaries[0].text
    infra = next(s for s in profile.skills if s.line == "Infra")
    assert infra.gated == ["AWS"]
    assert next(s for s in profile.skills if s.line == "Frontend").gated == []


def test_experience_and_projects(profile):
    assert [e.name for e in profile.experience] == ["Devnito", "Swift Reflex"]
    devnito = profile.experience[0]
    assert devnito.role == "Frontend & Mobile Engineer"
    assert devnito.start == "2024-11" and devnito.end == "present"
    assert [p.id for p in devnito.projects] == ["dedicate", "stanley-paden"]
    assert devnito.projects[0].label == "VC-backed asset management platform"
    assert profile.experience[1].projects[0].disclosure.startswith("Unpaid family work")


def test_claim_boundary(profile):
    cb = profile.experience[0].projects[0].claim_boundary
    assert any("Skyflow" in c for c in cb.cannot_claim)
    assert "estimated" in cb.required_qualifiers[0]
    # A project with no claim_boundary block still gets empty lists, not None.
    assert profile.experience[1].projects[0].claim_boundary.can_claim == []


def test_bullets(profile):
    dedicate = profile.experience[0].projects[0]
    assert [b.id for b in dedicate.bullets] == [
        "dedicate-frontend-scratch",
        "dedicate-caching",
    ]
    assert dedicate.bullets[0].priority == 1
    assert dedicate.bullets[0].status == "active"
    assert "estimated 50%" in dedicate.bullets[1].text
    blocked = profile.experience[0].projects[1].bullets[1]
    assert blocked.id == "stanley-iap" and blocked.status == "blocked"


def test_duplicate_bullet_id_rejected(tmp_path):
    dupe = tmp_path / "master.md"
    dupe.write_text(
        FIXTURE.read_text().replace("id: stanley-mobile", "id: dedicate-caching")
    )
    with pytest.raises(ValidationError, match="duplicate bullet id: dedicate-caching"):
        parse(dupe)
