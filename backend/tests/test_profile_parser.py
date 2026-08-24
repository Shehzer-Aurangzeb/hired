from pathlib import Path

import pytest

from app.profile_parser import SECTIONS, ProfileError, parse, parse_text

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


# ---------- the sixteen sections ----------

ALL_SECTIONS = "\n".join(
    f"# {s.title()}" + ("\nname: N" if s == "identity" else "") for s in SECTIONS
)


def test_every_section_name_parses_as_itself():
    """A heading the parser does not accept is silently a YAML comment."""
    profile = parse_text(ALL_SECTIONS)
    assert profile.identity.name == "N"
    # Empty everywhere else rather than missing, so nothing downstream branches
    # on "did they write the section at all".
    assert profile.titles == [] and profile.gaps == [] and profile.projects == []
    assert profile.meta.schema_version == 1


@pytest.mark.parametrize("section", SECTIONS)
def test_a_near_miss_on_any_section_is_caught(section):
    """
    Sixteen names, several of them four letters, all going through difflib at
    cutoff 0.75. A typo must still be a typo and not a comment that swallows
    everything under it.
    """
    typo = section[:-1]
    with pytest.raises(ProfileError) as error:
        parse_text(f"# Identity\nname: N\n\n# {typo.title()}\n- id: x\n")
    assert section.title() in error.value.message


def test_a_markdown_rule_between_sections_is_not_a_yaml_document_break():
    """
    A column-zero --- is a horizontal rule to the person typing and a second
    document to safe_load, which refuses the stream outright.
    """
    profile = parse_text("# Identity\nname: N\n\n---\n\n# Titles\n- id: a\n  text: A\n")
    assert profile.identity.name == "N"
    assert [t.id for t in profile.titles] == ["a"]


def test_the_rule_does_not_shift_error_lines():
    """Blanked rather than removed, so a line number still points at the line."""
    with pytest.raises(ProfileError) as error:
        parse_text("# Identity\nname: N\n\n---\n\n# Titles\n- id: a\n   bad: [\n")
    assert error.value.line == 8


# ---------- the Projects section ----------

LOOSE = """# Identity
name: N

# Projects

### Side Project
label: Mine
my_role: Solo
why_built: Wanted it
unverified:
  - Whether the deploy script still runs
bullets:
  - id: side-project-one
    text: Built it.
"""


def test_projects_needs_no_employer():
    profile = parse_text(LOOSE)
    assert profile.experience == []
    assert [p.id for p in profile.projects] == ["side-project"]
    project = profile.projects[0]
    assert project.my_role == "Solo" and project.why_built == "Wanted it"
    assert project.unverified and project.bullets[0].id == "side-project-one"


def test_all_projects_spans_both_lists():
    profile = parse(FIXTURE)
    from_experience = [p.id for e in profile.experience for p in e.projects]
    assert [p.id for p in profile.all_projects()] == from_experience + [
        p.id for p in profile.projects
    ]


def test_a_project_id_cannot_be_reused_across_the_two_lists():
    """A bullet id resolves to one project, so the same id twice is ambiguous."""
    text = """# Identity
name: N

# Experience
## Co
### Shared
bullets: []

# Projects
### Shared
bullets: []
"""
    with pytest.raises(ProfileError, match="duplicate project id: shared"):
        parse_text(text)


def test_a_bullet_id_cannot_be_reused_across_the_two_lists():
    text = """# Identity
name: N

# Experience
## Co
### One
bullets:
  - id: same
    text: A

# Projects
### Two
bullets:
  - id: same
    text: B
"""
    with pytest.raises(ProfileError, match="duplicate bullet id: same"):
        parse_text(text)


# ---------- what a paste actually looks like ----------


def test_a_code_fence_around_the_whole_file_is_stripped():
    """
    The briefing asks Claude for a markdown code block, so the fence arrives
    pasted with the contents. safe_load's answer to a backtick is "found
    character that cannot start any token", which helps nobody.
    """
    profile = parse_text("```markdown\n# Identity\nname: N\n\n# Titles\n- id: a\n  text: A\n```\n")
    assert profile.identity.name == "N" and profile.titles[0].id == "a"


def test_a_fence_inside_one_section_is_stripped_too():
    profile = parse_text("# Identity\nname: N\n\n# Titles\n```yaml\n- id: a\n  text: A\n```\n")
    assert profile.titles[0].id == "a"


def test_a_written_but_empty_list_is_empty_not_an_error():
    """
    Mid-draft is not a reason to refuse the only copy of the CV data. YAML reads
    a bare "cannot_claim:" as None, and Pydantic reads None as a type error.
    """
    profile = parse_text(
        "# Identity\nname: N\n\n# Experience\n## Co\n### P\n"
        "claim_boundary:\n  can_claim:\n  cannot_claim:\n"
        "bullets:\n  - id: p-one\n    text: x\n    tags:\n"
    )
    project = profile.experience[0].projects[0]
    assert project.claim_boundary.cannot_claim == [] and project.bullets[0].tags == []


def test_an_empty_section_body_is_still_empty():
    """The base class must not turn a whole missing section into something else."""
    profile = parse_text("# Identity\nname: N\n\n# Titles\n\n# Gaps\n")
    assert profile.titles == [] and profile.gaps == []


def test_enum_tokens_are_case_folded():
    """
    "Native" is the same answer as "native", and the code branches on these:
    a capitalised "Earned" certification would silently never print.
    """
    profile = parse_text(
        "# Identity\nname: N\n\n# Languages\n- name: English\n  level: Native\n\n"
        "# Certifications\n- name: C\n  status: Earned\n"
    )
    assert profile.languages[0].level == "native"
    assert profile.certifications[0].status == "earned"


def test_case_folding_does_not_excuse_a_wrong_value():
    from app.profile_parser import validate_text

    result = validate_text(
        "# Identity\nname: N\n\n# Languages\n- name: French\n  level: Professional working\n"
    )
    assert any("professional working" in w.message for w in result.warnings)

