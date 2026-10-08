"""
Ask: edit the profile by describing the change, instead of editing markdown.

The model never writes the file. It returns what it understood as a list of
typed changes, and this module renders the YAML and splices it in. Same bargain
as the CV selector, which answers in bullet ids: a model that cannot write the
file's shape cannot corrupt it.

Nothing is saved here. The spliced text comes back with a diff, the person keeps
talking until it is right, and confirming is an ordinary save through
PUT /api/profile/source, so it validates, takes the lock and appends a version.
"""

import difflib
import json
import re

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlmodel import select

from .db import SessionDep
from .model import generate_json
from .models import Profile
from .profile_parser import ProfileError, parse_text, replace_bullet_text, validate_text
from .tables import ProfileSource

router = APIRouter(tags=["ask"])

# What a change may do. Everything here either adds a fact or corrects one the
# person is describing. Loosening a claim boundary, clearing a gap or unblocking
# a bullet are deliberately absent: the profile can get more honest by itself and
# only ever gets bolder by hand.
OPS = (
    "add_skill_evidence",
    "update_skill_evidence",
    "add_skill_item",
    "add_bullet",
    "update_bullet",
)

LEVELS = ("familiar", "working", "advanced", "expert")
CONTEXTS = ("professional", "personal", "academic", "volunteer")

# A digit that follows a letter is part of a name: Auth0, S3, HTML5.
_NUMBER = re.compile(r"(?<![A-Za-z0-9])\d")


class Turn(BaseModel):
    role: str  # "you" | "model"
    text: str


class AskRequest(BaseModel):
    message: str
    # The whole conversation so far. Gemini is stateless, so every turn carries
    # it. Tokens grow, requests do not, and requests are what the free tier
    # rations.
    history: list[Turn] = []
    # What is already proposed and not yet saved. Replaying only the model's
    # prose lost the fields behind it: after answering a question mid-thread it
    # would say "added RTK Query at working level on two projects" and emit a
    # change carrying nothing but the name, because its own earlier answer was
    # never shown back to it.
    pending: list["Change"] = []


class Change(BaseModel):
    """
    Flat on purpose. A response schema wants concrete types, so one shape with
    optional fields beats a map the model fills in however it likes.
    """

    op: str
    target: str = ""
    level: str = ""
    last_used: str = ""
    years: float | None = None
    context: str = ""
    evidence: list[str] = []
    gated: bool = False
    line: str = ""
    project_id: str = ""
    bullet_id: str = ""
    text: str = ""
    metric_value: str = ""
    metric_source: str = ""
    metric_method: str = ""


AskRequest.model_rebuild()


class AskResponse(BaseModel):
    reply: str
    questions: list[str] = []
    changes: list[Change] = []
    # The profile as it would be. Null when nothing could be applied.
    text: str | None = None
    diff: list[dict] = []
    added: int = 0
    removed: int = 0
    # Why a change the model proposed was dropped. Shown, not swallowed.
    refused: list[str] = []


SCHEMA = {
    "type": "object",
    "properties": {
        "reply": {"type": "string"},
        "questions": {"type": "array", "items": {"type": "string"}},
        "changes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "op": {"type": "string", "enum": list(OPS)},
                    "target": {"type": "string"},
                    "level": {"type": "string"},
                    "last_used": {"type": "string"},
                    "years": {"type": "number"},
                    "context": {"type": "string"},
                    "evidence": {"type": "array", "items": {"type": "string"}},
                    "gated": {"type": "boolean"},
                    "line": {"type": "string"},
                    "project_id": {"type": "string"},
                    "bullet_id": {"type": "string"},
                    "text": {"type": "string"},
                    "metric_value": {"type": "string"},
                    "metric_source": {"type": "string"},
                    "metric_method": {"type": "string"},
                },
                "required": ["op"],
            },
        },
    },
    "required": ["reply", "changes"],
}

INSTRUCTIONS = """You are helping someone keep their master profile accurate. They
describe a change in plain language and you work out what it means for the file.

You never write the file. You return changes, and the application renders them.

The operations you may use:

  add_skill_evidence     target is the skill name. level, last_used, years,
                         context, evidence, gated.
  update_skill_evidence  same fields, for a skill that already has an entry.
                         Only send the fields that change.
  add_skill_item         line is the skills row it belongs in, target is the
                         item to add. Use the rows that already exist.
  add_bullet             project_id and text, plus metric_* when it has a number.
  update_bullet          bullet_id and text.

Rules:

- Never invent a fact. No years they did not give you, no project they did not
  name, no number. An absent field is correct; a plausible guess is something
  they have to defend in an interview.
- evidence holds project ids that already exist in the profile. If they name a
  project you cannot find, ask rather than guessing the id.
- level is one of familiar, working, advanced, expert:
    familiar  used it, would need the docs open, no deep questions
    working   shipped it to production, can answer normal questions
    advanced  primary tool, can defend the options they rejected
    expert    colleagues ask them, they know the internals
  If they have not told you which, ask. Do not assume working.
- An entry with no evidence ids means a tool they have used but cannot tie to a
  listed project. That is a real and useful answer. Do not refuse to record it,
  and do not invent a project to fill the gap.
- A bullet quoting a number needs metric_value, metric_source (measured,
  estimated or reported) and metric_method. When the source is estimated, the
  word "estimated" has to appear in the bullet text itself.
- Match the voice of the bullets you are shown: verb first, past tense, no
  first person, one accomplishment each.
- You may not loosen anything. Removing a cannot_claim, clearing a gap or
  unblocking a bullet are not operations you have.
- When the request is ambiguous, return no changes and ask. One or two questions,
  not a form. Being asked is why they are here rather than editing YAML.
- reply is one or two sentences, plain, addressed to them. Say what you changed
  or what you need. No flattery and no restating their message back."""


@router.post("/profile/ask")
def ask(body: AskRequest, session: SessionDep) -> AskResponse:
    text = (body.message or "").strip()
    if not text:
        raise HTTPException(422, "Say what you want to change.")

    row = session.exec(
        select(ProfileSource).order_by(ProfileSource.id.desc())
    ).first()
    if row is None:
        raise HTTPException(404, "No profile saved yet. There is nothing to change.")

    profile = parse_text(row.text)
    answer = generate_json(_prompt(profile, row.text, body), SCHEMA)

    said = " ".join([turn.text for turn in body.history] + [body.message])
    fresh, refused = _allowed(
        [Change.model_validate(c) for c in answer.get("changes") or []], profile, said
    )
    # A turn that only answers a question must not throw away what was already
    # agreed. Later wins on the same target, so a correction still lands.
    changes = _merge(body.pending, fresh)

    updated = row.text
    for change in changes:
        try:
            updated = _apply(updated, change)
        except ProfileError as error:
            refused.append(error.message)

    questions = [str(q) for q in answer.get("questions") or []]
    if updated == row.text:
        return AskResponse(
            reply=str(answer.get("reply", "")),
            questions=questions,
            refused=refused,
        )

    # A proposal that does not parse is not a proposal. Better to say so than to
    # hand over text that cannot be saved.
    result = validate_text(updated)
    if not result.ok:
        return AskResponse(
            reply=str(answer.get("reply", "")),
            questions=questions,
            refused=refused + [f"{issue.message}" for issue in result.errors],
        )

    lines = [
        {"op": line[0], "text": line}
        for line in difflib.unified_diff(
            row.text.splitlines(), updated.splitlines(), lineterm="", n=3
        )
        if not line.startswith(("---", "+++"))
    ]
    return AskResponse(
        reply=str(answer.get("reply", "")),
        questions=questions,
        changes=changes,
        text=updated,
        diff=lines,
        added=sum(1 for line in lines if line["op"] == "+"),
        removed=sum(1 for line in lines if line["op"] == "-"),
        refused=refused,
    )


def _key(change: Change) -> tuple[str, str]:
    """What makes two changes the same edit, so a correction replaces rather than repeats."""
    target = change.target or change.bullet_id or change.project_id or change.line
    return change.op, target.casefold()


def _merge(pending: list[Change], fresh: list[Change]) -> list[Change]:
    merged = {_key(change): change for change in pending}
    for change in fresh:
        existing = merged.get(_key(change))
        if existing is None:
            merged[_key(change)] = change
            continue
        # Only overwrite a field the new change actually filled in, so "make it
        # advanced" does not wipe the projects agreed three turns ago.
        filled = {
            name: value
            for name, value in change.model_dump().items()
            if value not in ("", [], None, False)
        }
        merged[_key(change)] = existing.model_copy(update=filled)
    return list(merged.values())


def _prompt(profile: Profile, source: str, body: AskRequest) -> str:
    """
    The whole file, plus the conversation, plus real bullets as the style guide.

    Showing six of their own bullets carries voice and length better than any
    rule could: they are verb-first, one claim each, and the ones with a number
    already say "estimated" out loud where the metric says estimated.
    """
    samples = [
        bullet.text
        for project in profile.all_projects()
        for bullet in project.bullets
        if bullet.status != "blocked"
    ][:6]
    known = {
        "project_ids": [p.id for p in profile.all_projects()],
        "skills_lines": [row.line for row in profile.skills],
        "skills_with_evidence": [s.name for s in profile.skill_evidence],
    }
    talk = "\n".join(f"{turn.role}: {turn.text}" for turn in body.history)
    # The fields, not just the prose. Without these a later turn has to guess
    # back what it already worked out, and it guesses badly.
    proposed = json.dumps(
        [
            {k: v for k, v in change.model_dump().items() if v not in ("", [], None, False)}
            for change in body.pending
        ]
    )
    return (
        f"{INSTRUCTIONS}\n\nHOW THEIR BULLETS READ:\n" + "\n\n".join(samples)
        + f"\n\nWHAT EXISTS ALREADY:\n{json.dumps(known)}"
        + f"\n\nTHE PROFILE:\n{source}"
        + (f"\n\nCONVERSATION SO FAR:\n{talk}" if talk else "")
        + (
            f"\n\nALREADY PROPOSED, NOT YET SAVED:\n{proposed}"
            "\nReturn a change for anything you are adding or correcting. Leave the rest"
            " alone; what is listed here is kept."
            if body.pending
            else ""
        )
        + f"\n\nTHEY SAY:\n{body.message}"
    )


def _allowed(
    changes: list[Change], profile: Profile, said: str = ""
) -> tuple[list[Change], list[str]]:
    """
    The guard. Everything here is checked in code rather than asked for in the
    prompt, because a prompt is a request and this is a rule.
    """
    ok: list[Change] = []
    refused: list[str] = []
    # A duration can only have come from the person. Asked for a level and a
    # date, the model answered with "years: 3" on the first real call, which is
    # the invention this whole app exists to prevent. No digit in anything they
    # typed means there was nothing to round, so the field goes.
    told_a_number = bool(re.search(r"\d", said))
    projects = {p.id for p in profile.all_projects()}
    lines = {row.line.casefold() for row in profile.skills}
    bullets = {b.id for p in profile.all_projects() for b in p.bullets}

    for change in changes:
        if change.op not in OPS:
            refused.append(f'"{change.op}" is not something Ask can do.')
            continue
        if change.level and change.level not in LEVELS:
            refused.append(f'"{change.level}" is not a level. Expected one of {", ".join(LEVELS)}.')
            continue
        if change.context and change.context not in CONTEXTS:
            refused.append(f'"{change.context}" is not a context.')
            continue

        missing = [p for p in change.evidence if p not in projects]
        if missing:
            refused.append(f'No project called {", ".join(missing)} in the profile.')
            continue

        if change.op == "add_skill_item" and not change.line.strip():
            refused.append(
                f'Did not add "{change.target}" to Skills: no row was named. '
                f'The rows are {", ".join(row.line for row in profile.skills)}.'
            )
            continue
        if change.op == "add_skill_item" and change.line.casefold() not in lines:
            refused.append(f'There is no "{change.line}" row in Skills.')
            continue
        if change.op == "add_bullet" and change.project_id not in projects:
            refused.append(f'No project called "{change.project_id}".')
            continue
        if change.op == "update_bullet" and change.bullet_id not in bullets:
            refused.append(f'No bullet called "{change.bullet_id}".')
            continue

        if change.op in ("add_bullet", "update_bullet"):
            if _NUMBER.search(change.text) and change.metric_source not in (
                "measured",
                "estimated",
                "reported",
            ):
                refused.append(
                    "That bullet quotes a number with no source. A number you cannot "
                    "place is a number you will be asked about."
                )
                continue
            if change.metric_source == "estimated" and "estimated" not in change.text.lower():
                refused.append(
                    'An estimated number has to say "estimated" in the bullet, because '
                    "the bullet is what gets read."
                )
                continue

        if change.op in ("add_skill_evidence", "update_skill_evidence") and not (
            change.level or change.evidence or change.last_used or change.context
        ):
            refused.append(
                f'Nothing recorded for "{change.target}": no level, no project, no date. '
                "A name on its own says less than leaving it out."
            )
            continue

        if change.years is not None and not told_a_number:
            refused.append(
                f'Dropped the years on "{change.target}". You did not give a number, '
                "and a duration nobody said is one you have to defend."
            )
            change = change.model_copy(update={"years": None})

        ok.append(change)
    return ok, refused


def _apply(source: str, change: Change) -> str:
    if change.op == "add_skill_evidence":
        return _append_to_section(source, "Skill Evidence", _evidence_yaml(change))
    if change.op == "update_skill_evidence":
        return _replace_evidence(source, change)
    if change.op == "add_skill_item":
        return _add_skill_item(source, change.line, change.target)
    if change.op == "add_bullet":
        return _append_bullet(source, change)
    if change.op == "update_bullet":
        return replace_bullet_text(source, change.bullet_id, change.text)
    raise ProfileError(f'"{change.op}" is not something Ask can do.')


def _evidence_yaml(change: Change) -> list[str]:
    out = [f"- name: {change.target}"]
    if change.years is not None:
        out.append(f"  years: {change.years:g}")
    if change.last_used:
        out.append(f"  last_used: {change.last_used}")
    if change.level:
        out.append(f"  level: {change.level}")
    if change.context:
        out.append(f"  context: {change.context}")
    if change.evidence:
        out.append(f"  evidence: [{', '.join(change.evidence)}]")
    if change.gated:
        out.append("  gated: true")
    return out


def _section_bounds(lines: list[str], name: str) -> tuple[int, int]:
    """
    Where a section's body starts and ends. The end is one past the last line
    with anything on it, so an insert lands before the blank and the rule that
    separate sections rather than after them.
    """
    try:
        start = lines.index(f"# {name}") + 1
    except ValueError as error:
        raise ProfileError(f'No "# {name}" section in the profile.') from error
    end = len(lines)
    for i in range(start, len(lines)):
        if lines[i].startswith("# ") or lines[i].rstrip() == "---":
            end = i
            break
    while end > start and not lines[end - 1].strip():
        end -= 1
    return start, end


def _append_to_section(source: str, name: str, block: list[str]) -> str:
    lines = source.split("\n")
    _, end = _section_bounds(lines, name)
    return "\n".join(lines[:end] + block + lines[end:])


def _replace_evidence(source: str, change: Change) -> str:
    """
    Swap one entry for a rewritten one, leaving every other line untouched. The
    entry runs from its `- name:` to the next one at the same indent.
    """
    lines = source.split("\n")
    start, end = _section_bounds(lines, "Skill Evidence")
    head = None
    for i in range(start, end):
        if lines[i].strip().casefold() == f"- name: {change.target}".casefold():
            head = i
            break
    if head is None:
        raise ProfileError(f'No entry for "{change.target}" in Skill Evidence.')

    tail = end
    for i in range(head + 1, end):
        if lines[i].startswith("- "):
            tail = i
            break

    # Keep whatever they already wrote and let the change win field by field, so
    # a correction to the level does not quietly drop the years.
    kept = {}
    for line in lines[head + 1 : tail]:
        if ":" in line:
            key, _, value = line.strip().partition(":")
            kept[key.strip()] = value.strip()
    merged = Change(
        op=change.op,
        target=change.target,
        level=change.level or kept.get("level", ""),
        last_used=change.last_used or kept.get("last_used", ""),
        years=change.years if change.years is not None else _float(kept.get("years")),
        context=change.context or kept.get("context", ""),
        evidence=change.evidence or _list(kept.get("evidence")),
        gated=change.gated or kept.get("gated") == "true",
    )
    return "\n".join(lines[:head] + _evidence_yaml(merged) + lines[tail:])


def _float(value: str | None) -> float | None:
    try:
        return float(value) if value else None
    except ValueError:
        return None


def _list(value: str | None) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in value.strip("[]").split(",") if part.strip()]


def _add_skill_item(source: str, line_name: str, item: str) -> str:
    """
    Add one item to a Skills row. The list can wrap over several lines, so this
    works on the whole `items: [...]` span rather than a single line.
    """
    lines = source.split("\n")
    start, end = _section_bounds(lines, "Skills")
    head = None
    for i in range(start, end):
        if lines[i].strip().casefold() == f"- line: {line_name}".casefold():
            head = i
            break
    if head is None:
        raise ProfileError(f'There is no "{line_name}" row in Skills.')

    for i in range(head + 1, end):
        if lines[i].strip().startswith("items:"):
            close = i
            while close < end and "]" not in lines[close]:
                close += 1
            if close >= end:
                raise ProfileError(f'The items list for "{line_name}" is not closed.')
            if re.search(rf"\b{re.escape(item)}\b", "\n".join(lines[i : close + 1])):
                raise ProfileError(f'"{item}" is already in the {line_name} row.')
            lines[close] = lines[close].replace("]", f", {item}]", 1)
            return "\n".join(lines)
    raise ProfileError(f'The "{line_name}" row has no items list.')


def _append_bullet(source: str, change: Change) -> str:
    """
    Add a bullet to a project's existing `bullets:` block, with an id derived
    from the project and the opening words. The app generates the id rather than
    the model, so it cannot collide with one already in the file.
    """
    lines = source.split("\n")
    anchor = None
    for i, line in enumerate(lines):
        if line.strip() == f"id: {change.project_id}" or (
            line.startswith("### ") and _slug(line[4:]) == change.project_id
        ):
            anchor = i
            break
    if anchor is None:
        raise ProfileError(f'No project called "{change.project_id}".')

    start = None
    for i in range(anchor, len(lines)):
        if lines[i].startswith(("### ", "## ", "# ")) and i > anchor:
            break
        if lines[i].rstrip() == "bullets:":
            start = i
            break
    if start is None:
        raise ProfileError(f'"{change.project_id}" has no bullets block to add to.')

    end = len(lines)
    for i in range(start + 1, len(lines)):
        if lines[i].strip() and not lines[i].startswith(" "):
            end = i
            break
    while end > start and not lines[end - 1].strip():
        end -= 1

    existing = set(re.findall(r"^\s*- id:\s*(\S+)", source, re.M))
    bullet_id = _unique(f"{change.project_id}-{_slug(change.text, words=2)}", existing)
    block = [f"  - id: {bullet_id}", f"    text: {_quote(change.text)}"]
    if change.metric_value:
        block.append("    metric:")
        block.append(f"      value: {_quote(change.metric_value)}")
        block.append(f"      source: {change.metric_source or 'none'}")
        if change.metric_method:
            block.append(f"      method: {_quote(change.metric_method)}")
    return "\n".join(lines[:end] + block + lines[end:])


def _quote(text: str) -> str:
    """A colon turns a scalar into a mapping, which is the trap people hit most."""
    return f"'{text.replace(chr(39), chr(39) * 2)}'" if ":" in text else text


def _slug(text: str, words: int = 0) -> str:
    parts = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-").split("-")
    return "-".join(parts[:words] if words else parts)


def _unique(candidate: str, taken: set[str]) -> str:
    if candidate not in taken:
        return candidate
    n = 2
    while f"{candidate}-{n}" in taken:
        n += 1
    return f"{candidate}-{n}"
