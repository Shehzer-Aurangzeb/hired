"""
The warnings in validate_text.

Every one of these is a warning and not an error on purpose: the profile row is
the only copy of the CV data, and a save refused over a missing qualifier costs
more than it protects. They get promoted when there is a generator to protect.

CLEAN below is the shipped template, which is the zero-warning baseline. Each
test breaks exactly one thing, so a warning appearing is that check and not a
side effect of the fixture.
"""

from pathlib import Path

import pytest

from app.profile_parser import MAX_WARNINGS, validate_text

CLEAN = Path(__file__).parents[2] / "docs" / "master_template.md"

BASE = """# Identity
name: N

# Skills
- line: Frontend
  items: [React]

# Experience
## Co
start: 2024-01

### Thing
claim_boundary:
  cannot_claim:
    - The part somebody else wrote
bullets:
  - id: thing-one
    text: Built a thing.

# Gaps
- skill: Kubernetes
  status: none
"""


def messages(text: str) -> list[str]:
    result = validate_text(text)
    assert result.ok, result.errors
    return [issue.message for issue in result.warnings]


def only(text: str) -> str:
    """The single warning a mutation is supposed to produce."""
    found = messages(text)
    assert len(found) == 1, found
    return found[0]


def test_the_baseline_is_silent():
    assert messages(BASE) == []


def test_the_shipped_template_is_silent():
    """Every check's "does not fire" case, in one document."""
    assert messages(CLEAN.read_text(encoding="utf-8")) == []


# ---------- claims ----------


NO_BOUNDARY = "claim_boundary:\n  cannot_claim:\n    - The part somebody else wrote\n"


def test_cannot_claim_empty_on_a_project_with_bullets():
    text = BASE.replace(NO_BOUNDARY, "")
    found = messages(text)
    assert any("cannot_claim is the half that protects you" in m for m in found)
    assert any("Thing" in m for m in found)


def test_cannot_claim_is_not_asked_of_a_project_with_no_bullets():
    text = BASE.replace("bullets:\n  - id: thing-one\n    text: Built a thing.\n", "").replace(
        NO_BOUNDARY, ""
    )
    assert not any("cannot_claim" in m for m in messages(text))


# ---------- numbers ----------


def test_a_number_with_no_metric():
    text = BASE.replace("Built a thing.", "Cut load time by 40 percent.")
    assert "needs a source you can name out loud" in only(text)


def test_a_number_with_a_metric_is_fine():
    text = BASE.replace(
        "    text: Built a thing.",
        "    text: Cut load time by 40 percent.\n"
        "    metric:\n      value: 40 percent\n      source: measured",
    )
    assert messages(text) == []


def test_an_estimate_that_does_not_say_so_in_the_text():
    text = BASE.replace(
        "    text: Built a thing.",
        "    text: Cut load time by roughly 40 percent.\n"
        "    metric:\n      value: 40 percent\n      source: estimated",
    )
    assert "qualifier has to travel with the claim" in only(text)


def test_an_estimate_that_says_so_is_fine():
    text = BASE.replace(
        "    text: Built a thing.",
        "    text: Cut load time by an estimated 40 percent.\n"
        "    metric:\n      value: 40 percent\n      source: estimated",
    )
    assert messages(text) == []


# ---------- blocked bullets ----------


def test_blocked_with_no_reason():
    text = BASE.replace(
        "    text: Built a thing.", "    status: blocked\n    text: Built a thing."
    )
    assert "Nobody can act on it later" in only(text)


def test_blocked_with_no_text():
    text = BASE.replace(
        "    text: Built a thing.",
        "    status: blocked\n    blocked_reason: No access to the old dashboard\n    text: ''",
    )
    assert "nothing to check" in only(text)


def test_blocked_with_both_is_fine():
    text = BASE.replace(
        "    text: Built a thing.",
        "    status: blocked\n    blocked_reason: No access to the old dashboard\n"
        "    text: Built a thing.",
    )
    assert messages(text) == []


# ---------- wording ----------


def test_an_em_dash_is_reported_with_its_line():
    text = BASE.replace("Built a thing.", "Built a thing — quickly.")
    result = validate_text(text)
    issue = next(i for i in result.warnings if "em dash" in i.message)
    lines = text.split("\n")
    assert issue.line == lines.index("    text: Built a thing — quickly.") + 1


def test_an_en_dash_is_reported_too():
    text = BASE.replace("Built a thing.", "Built it 2024–2025.")
    assert any("en dash" in m for m in messages(text))


def test_a_banned_word_in_a_bullet():
    text = BASE.replace(
        "# Gaps", "# Rules\nbanned_words:\n  - spearheaded\n\n# Gaps"
    ).replace("Built a thing.", "Spearheaded a thing.")
    assert 'banned word: "spearheaded"' in only(text)


def test_a_banned_word_somewhere_other_than_a_bullet_is_not_flagged():
    text = BASE.replace("# Gaps", "# Rules\nbanned_words:\n  - spearheaded\n\n# Gaps")
    assert messages(text) == []


# ---------- skill evidence ----------


def evidence(body: str) -> str:
    return BASE.replace("# Experience", f"# Skill Evidence\n{body}\n# Experience")


def test_evidence_for_a_skill_that_is_in_no_skills_row():
    assert "Probably a typo" in only(evidence("- name: Reakt\n  evidence: [thing]\n"))


def test_a_gated_skill_with_no_evidence_can_never_print():
    text = evidence("- name: React\n  gated: true\n  evidence: []\n")
    assert "the gate can never open" in only(text)


def test_evidence_pointing_at_a_project_that_does_not_exist():
    text = evidence("- name: React\n  evidence: [thign]\n")
    assert "Stale reference" in only(text)


def test_evidence_pointing_at_a_standalone_project_resolves():
    """The two project lists share one namespace, so either side counts."""
    text = (
        BASE.replace(
            "# Experience",
            "# Skill Evidence\n- name: React\n  evidence: [loose]\n\n# Experience",
        )
        + "\n# Projects\n\n### Loose\n"
        + "claim_boundary:\n  cannot_claim:\n    - Anything operational\n"
    )
    assert messages(text) == []


# ---------- enums ----------


@pytest.mark.parametrize(
    "insert, allowed",
    [
        ("# Skill Evidence\n- name: React\n  level: wizard\n\n", "familiar, working"),
        ("# Skill Evidence\n- name: React\n  context: spiritual\n\n", "professional, personal"),
        ("# Certifications\n- name: C\n  status: pending\n\n", "earned, in_progress"),
        ("# Publications\n- title: T\n  type: tweet\n\n", "talk, article"),
        ("# Languages\n- name: English\n  level: mother tongue\n\n", "native, fluent"),
    ],
)
def test_a_value_outside_its_set_names_the_set(insert, allowed):
    message = only(BASE.replace("# Experience", insert + "# Experience"))
    assert "One of:" in message and allowed in message


def test_an_empty_enum_is_not_a_wrong_one():
    """Every field is optional, so unwritten must never read as invalid."""
    text = BASE.replace("# Experience", "# Languages\n- name: English\n\n# Experience")
    assert messages(text) == []


def test_project_and_employment_enums():
    text = BASE.replace("start: 2024-01", "start: 2024-01\nemployment_type: fulltime").replace(
        "### Thing", "### Thing\nstatus: shipping"
    )
    found = messages(text)
    assert any("employment_type" in m for m in found)
    assert any('Project "Thing" status' in m for m in found)


def test_a_metric_source_outside_its_set():
    text = BASE.replace(
        "    text: Built a thing.",
        "    text: Built a thing.\n    metric:\n      value: x\n      source: vibes",
    )
    assert "metric source" in only(text)


# ---------- order and coverage ----------


def test_employers_out_of_order():
    text = BASE.replace(
        "# Gaps",
        "## Older Co\nstart: 2026-01\n\n### Other\nclaim_boundary:\n  cannot_claim:\n"
        "    - Anything before you joined\nbullets: []\n\n# Gaps",
    )
    assert "not newest first" in only(text)


def test_no_gaps_section():
    text = BASE.replace("# Gaps\n- skill: Kubernetes\n  status: none\n", "")
    assert "degrades to guessing" in only(text)


# ---------- the summary ----------


def test_the_summary_counts_both_project_lists():
    text = BASE + (
        "\n# Projects\n\n### Loose\n"
        "unverified:\n  - Check the deploy script\n"
        "claim_boundary:\n  cannot_claim:\n    - Anything operational\n"
    )
    summary = validate_text(text).summary
    assert summary.projects == 1 and summary.projects_total == 2
    assert summary.gaps == 1 and summary.unverified == 1
    assert summary.skills_evidenced == 0


# ---------- the cap ----------


def test_the_tail_is_collapsed():
    bullets = "\n".join(
        f"  - id: thing-{n}\n    text: Shipped {n} of them." for n in range(MAX_WARNINGS + 5)
    )
    text = BASE.replace("  - id: thing-one\n    text: Built a thing.", bullets)
    found = messages(text)
    assert len(found) == MAX_WARNINGS + 1
    assert found[-1] == "and 5 more, hidden so this list stays readable."


# ---------- the existing fixture ----------

FIXTURE = Path(__file__).parent / "fixtures" / "master.md"


def test_the_fixture_still_saves_and_what_it_warns_about():
    """
    Pinned rather than fixed. The fixture is a real profile written before any of
    these checks existed, and it is the proof that such a file still saves: seven
    warnings, zero errors, ok=True. Changing the fixture to silence them would
    throw away exactly the case worth keeping. It was seven until enum tokens
    started case-folding, which took "Native" out of the list.
    """
    result = validate_text(FIXTURE.read_text(encoding="utf-8"))
    assert result.ok and result.errors == []
    assert len(result.warnings) == 6
