from pathlib import Path

import pytest

from app.profile_parser import ProfileError, parse, parse_text

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


def test_links_parse_in_all_three_shapes(profile):
    assert [(link.label, link.url) for link in profile.identity.links] == [
        ("Dribbble", "dribbble.com/test"),
        ("Stack Overflow", "stackoverflow.com/users/1/test"),
        # A bare URL takes its label from the host, with www dropped.
        ("medium.com", "https://www.medium.com/@test"),
    ]
    dedicate = profile.experience[0].projects[0]
    assert [link.label for link in dedicate.links] == ["Live", "Case study"]
    assert profile.experience[0].projects[1].links == []


def test_education_certifications_languages(profile):
    assert profile.education[0].school == "Concordia University"
    assert profile.education[0].start == "2018-09"
    assert profile.certifications[0].issuer == "Amazon Web Services"
    assert [lang.name for lang in profile.languages] == ["English", "French"]


def test_duplicate_bullet_id_rejected():
    dupe = FIXTURE.read_text().replace("id: stanley-mobile", "id: dedicate-caching")
    with pytest.raises(ProfileError, match="duplicate bullet id: dedicate-caching"):
        parse_text(dupe)


def test_duplicate_project_id_rejected():
    dupe = FIXTURE.read_text().replace("### Stanley Paden", "### Dedicate")
    with pytest.raises(ProfileError, match="duplicate project id: dedicate"):
        parse_text(dupe)


# ---------- the hardening ----------


def test_yaml_error_points_at_the_real_file_line():
    """The whole reason the parser tracks offsets: a usable line number."""
    lines = FIXTURE.read_text().split("\n")
    at = next(i for i, line in enumerate(lines) if "must always carry" in line)
    # Drop the outer quotes and the value becomes two YAML scalars on one line.
    lines[at] = lines[at].replace("- '", "- ").replace("'\n", "").rstrip("'")

    with pytest.raises(ProfileError) as caught:
        parse_text("\n".join(lines))
    assert caught.value.line == at + 1


def test_a_stray_hash_comment_is_not_a_section():
    """It used to swallow everything below it. Now it is just a YAML comment."""
    text = FIXTURE.read_text().replace(
        "# Titles", "# TODO come back to the titles\n\n# Titles"
    )
    assert len(parse_text(text).titles) == 2


def test_a_misspelled_section_is_caught_not_ignored():
    text = FIXTURE.read_text().replace("# Experience", "# Experiance")
    with pytest.raises(ProfileError, match='Did you mean "# Experience"'):
        parse_text(text)


def test_repeated_section_is_rejected():
    with pytest.raises(ProfileError, match="appears twice"):
        parse_text(FIXTURE.read_text() + "\n# Languages\n- name: Spanish\n")


def test_crlf_and_bom_survive():
    text = "\ufeff" + FIXTURE.read_text().replace("\n", "\r\n")
    assert parse_text(text).identity.name == "Test Person"


def test_missing_identity_says_so():
    with pytest.raises(ProfileError, match='No "# Identity" section'):
        parse_text("# Titles\n- id: a\n  text: b\n")


def test_optional_identity_fields_are_optional():
    profile = parse_text("# Identity\nname: Someone\n")
    assert profile.identity.email == "" and profile.identity.links == []
