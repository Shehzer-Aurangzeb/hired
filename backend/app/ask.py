"""Edit the profile by describing a change: the model returns typed changes, this
module splices the YAML in and returns a diff. Nothing is saved here."""

import difflib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlmodel import select

from .db import SessionDep
from .model import generate_json
from .models import Profile
from .profile_parser import ProfileError, parse_text, replace_bullet_text, validate_text
from .tables import ProfileSource

router = APIRouter(tags=["ask"])

# Only adds or corrects facts. Loosening a claim boundary, clearing a gap or
# unblocking a bullet is deliberately left to hand edits.
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
# A year, a month name, or "last week"-style recency. Anything vaguer is not a date.
_DATE = re.compile(
    r"\b(20\d\d|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec"
    r"|today|yesterday|last (week|month|year)|this (week|month|year))",
    re.I,
)


class Turn(BaseModel):
    role: str  # "you" | "model"
    text: str


class AskRequest(BaseModel):
    message: str
    # The model is stateless, so every turn resends the conversation.
    history: list[Turn] = []
    # Proposed but unsaved changes. Resent as fields, because replaying only the
    # prose made the model drop them on later turns.
    pending: list["Change"] = []


class EditRequest(BaseModel):
    """A proposal after the person has corrected it. No message, no history."""

    changes: list["Change"] = []


class Change(BaseModel):
    """Flat on purpose: a response schema wants one concrete shape."""

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
EditRequest.model_rebuild()


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


SOURCES = ("measured", "estimated", "reported")

# One JSON type per field. Shared, so a field means the same thing in every op.
FIELD = {
    "target": {"type": "string"},
    "level": {"type": "string", "enum": list(LEVELS)},
    "last_used": {"type": "string"},
    "years": {"type": "number"},
    "context": {"type": "string", "enum": list(CONTEXTS)},
    "evidence": {"type": "array", "items": {"type": "string"}},
    "gated": {"type": "boolean"},
    "line": {"type": "string"},
    "project_id": {"type": "string"},
    "bullet_id": {"type": "string"},
    "text": {"type": "string"},
    "metric_value": {"type": "string"},
    "metric_source": {"type": "string", "enum": list(SOURCES)},
    "metric_method": {"type": "string"},
}

# (must have, may have) per op. An op is only asked for the fields it uses, so a
# date cannot land in `years` and a bullet cannot arrive with a skill level.
OP_FIELDS = {
    "add_skill_evidence": (
        ["target", "level"],
        ["last_used", "years", "context", "evidence", "gated"],
    ),
    "update_skill_evidence": (
        ["target"],
        ["level", "last_used", "years", "context", "evidence", "gated"],
    ),
    "add_skill_item": (["line", "target"], []),
    "add_bullet": (
        ["project_id", "text"],
        ["metric_value", "metric_source", "metric_method"],
    ),
    "update_bullet": (
        ["bullet_id", "text"],
        ["metric_value", "metric_source", "metric_method"],
    ),
}

# Call one: which op, or "ask" when something is still missing.
ROUTE_SCHEMA = {
    "type": "object",
    "properties": {
        "op": {"type": "string", "enum": [*OPS, "ask"]},
        "reply": {"type": "string"},
        "questions": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["op", "reply"],
}


def schema_for(op: str) -> dict:
    """Call two: the changes array, holding only this op's fields."""
    required, optional = OP_FIELDS[op]
    return {
        "type": "object",
        "properties": {
            "changes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {f: FIELD[f] for f in required + optional},
                    "required": required,
                },
            }
        },
        "required": ["changes"],
    }


INSTRUCTIONS = """You are helping someone keep their master profile accurate. They
describe a change in plain language and you work out what it means for the file.

You never write the file. You return changes, and the application renders them.

You answer twice: first which one operation this is, or "ask" if anything is
still missing, then that operation's fields.

The operations, and when each one is the answer:

  add_skill_evidence     They used a tool. "I used X", "X on these projects",
                         "I'm advanced at X". Naming projects is evidence for
                         the skill, not a request for a bullet.
  update_skill_evidence  Same, for a skill already in Skill Evidence.
  add_skill_item         They want a name listed in Skills, with no claim about
                         depth. "add X to the list".
  add_bullet             They describe something they did on a project, in a
                         sentence that belongs on a CV. "add a bullet about...".
  update_bullet          They want an existing bullet reworded.

Mentioning a project is not what makes it a bullet. A bullet is an
accomplishment with a verb; a skill with projects beside it is evidence.

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
- When the request is ambiguous, set op to "ask" and ask. One or two questions,
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
    turns = [("user" if t.role == "you" else "model", t.text) for t in body.history]
    turns.append(("user", text))
    prompt = _prompt(profile, row.text, body)

    # Two calls: which kind of change, then that kind's fields. One call with
    # every field at once had the model putting dates in `years`.
    route = generate_json(prompt, ROUTE_SCHEMA, turns)
    op = str(route.get("op", "ask"))
    reply = str(route.get("reply", ""))
    questions = [str(q) for q in route.get("questions") or []]

    answer = {"changes": []}
    unknown = [] if op in OPS or op == "ask" else [f'"{op}" is not something Ask can do.']
    if op in OPS:
        answer = generate_json(f"{prompt}\n\nRETURN {op} CHANGES ONLY.", schema_for(op), turns)
        # An empty array satisfies the schema, so silence has to be reported.
        if not answer.get("changes"):
            unknown.append(f"Read that as {op} but could not fill it in. Try saying it another way.")
    _log(body, {"op": op, "reply": reply, "questions": questions, **answer})

    said = " ".join([turn.text for turn in body.history] + [body.message])
    fresh, refused = _allowed(
        [
            Change.model_validate({"op": op, **c})
            for c in answer.get("changes") or []
        ],
        profile,
        said,
    )
    # Keep what was already agreed; a later change on the same target wins.
    changes = _merge(body.pending, fresh)

    return _respond(row.text, changes, unknown + refused, reply=reply, questions=questions)


@router.post("/profile/ask/edit")
def edit(body: EditRequest, session: SessionDep) -> AskResponse:
    """
    Re-apply a proposal the person has edited by hand. Same guards, same splice,
    no model call. Values they typed are their own, so the "nobody said this"
    checks do not run on them.
    """
    row = session.exec(select(ProfileSource).order_by(ProfileSource.id.desc())).first()
    if row is None:
        raise HTTPException(404, "No profile saved yet. There is nothing to change.")

    changes, refused = _allowed(body.changes, parse_text(row.text), said="", trusted=True)
    return _respond(row.text, changes, refused, reply="", questions=[])


def _respond(
    source: str,
    changes: list[Change],
    refused: list[str],
    reply: str,
    questions: list[str],
) -> AskResponse:
    """Splice the changes in, then hand back the diff. Nothing is saved here."""
    updated = source
    for change in changes:
        try:
            updated = _apply(updated, change)
        except ProfileError as error:
            refused.append(error.message)

    if updated == source:
        return AskResponse(reply=reply, questions=questions, refused=refused)

    # Never hand back text that cannot be saved.
    result = validate_text(updated)
    if not result.ok:
        return AskResponse(
            reply=reply,
            questions=questions,
            refused=refused + [issue.message for issue in result.errors],
        )

    lines = [
        {"op": line[0], "text": line}
        for line in difflib.unified_diff(
            source.splitlines(), updated.splitlines(), lineterm="", n=3
        )
        if not line.startswith(("---", "+++"))
    ]
    return AskResponse(
        reply=reply,
        questions=questions,
        changes=changes,
        text=updated,
        diff=lines,
        added=sum(1 for line in lines if line["op"] == "+"),
        removed=sum(1 for line in lines if line["op"] == "-"),
        refused=refused,
    )


def _key(change: Change) -> tuple[str, str]:
    target = change.target or change.bullet_id or change.project_id or change.line
    return change.op, target.casefold()


def _merge(pending: list[Change], fresh: list[Change]) -> list[Change]:
    merged = {_key(change): change for change in pending}
    for change in fresh:
        existing = merged.get(_key(change))
        if existing is None:
            merged[_key(change)] = change
            continue
        # Only overwrite fields the new change filled in.
        filled = {
            name: value
            for name, value in change.model_dump().items()
            if value not in ("", [], None, False)
        }
        merged[_key(change)] = existing.model_copy(update=filled)
    return list(merged.values())


# ponytail: one JSONL line per turn, no rotation, no levels. It is for reading
# back what the model said while tuning the prompt, not for running anything on.
# Add rotation if it ever gets big enough to care about.
LOG = Path(__file__).resolve().parents[1] / ".ask-log.jsonl"


def _log(body: AskRequest, answer: dict) -> None:
    """What was asked and what came back, raw, before any guard touches it."""
    try:
        line = {
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "message": body.message,
            "turns": len(body.history),
            "pending": [c.model_dump(exclude_defaults=True) for c in body.pending],
            "answer": answer,
        }
        with LOG.open("a") as out:
            out.write(json.dumps(line) + "\n")
    except Exception:  # noqa: BLE001
        pass  # A log that breaks the feature is worse than no log.


def _text_of(lines: list[str], name: str) -> str:
    start, end = _section_bounds(lines, name)
    return "\n".join(lines[start:end])


def _context(profile: Profile, source: str, body: AskRequest) -> str:
    """
    What the question needs, not the whole file. Skills and Skill Evidence are a
    few hundred lines and every skill op touches them. A project's bullets only
    travel when the conversation names that project, which is most of the file.

    # ponytail: substring match on id and name. A project nobody names is one the
    # model has to ask about, which is what we want it to do anyway.
    """
    lines = source.split("\n")
    said = " ".join([turn.text for turn in body.history] + [body.message]).casefold()
    blocks = [
        f"# Skills\n{_text_of(lines, 'Skills')}",
        f"# Skill Evidence\n{_text_of(lines, 'Skill Evidence')}",
    ]
    for project in profile.all_projects():
        if project.id.casefold() not in said and project.name.casefold() not in said:
            continue
        blocks.append(
            "PROJECT "
            + json.dumps(
                {
                    "id": project.id,
                    "name": project.name,
                    "claim_boundary": project.claim_boundary.model_dump(),
                    "bullets": [
                        {"id": b.id, "text": b.text, "status": b.status}
                        for b in project.bullets
                    ],
                }
            )
        )
    return "\n\n".join(blocks)


def _prompt(profile: Profile, source: str, body: AskRequest) -> str:
    """The briefing: rules, voice, and the slice of the file this question needs.
    The conversation itself travels as real turns, not quoted in here."""
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
    proposed = json.dumps(
        [
            {k: v for k, v in change.model_dump().items() if v not in ("", [], None, False)}
            for change in body.pending
        ]
    )
    return (
        f"{INSTRUCTIONS}\n\nHOW THEIR BULLETS READ:\n" + "\n\n".join(samples)
        + f"\n\nWHAT EXISTS ALREADY:\n{json.dumps(known)}"
        + f"\n\nTHE PROFILE:\n{_context(profile, source, body)}"
        + (
            f"\n\nALREADY PROPOSED, NOT YET SAVED:\n{proposed}"
            "\nReturn a change for anything you are adding or correcting. Leave the rest"
            " alone; what is listed here is kept."
            if body.pending
            else ""
        )
    )


def _allowed(
    changes: list[Change], profile: Profile, said: str = "", trusted: bool = False
) -> tuple[list[Change], list[str]]:
    """
    Enforce in code what the prompt only asks for. Returns (allowed, refusals).

    `trusted` means the person typed these values, so the checks for numbers and
    dates nobody gave are skipped. Everything structural still runs.
    """
    ok: list[Change] = []
    refused: list[str] = []
    # Years and dates can only come from the person. With no digit and no date in
    # what they said, the model invented it, so the field is dropped.
    told_a_number = trusted or bool(re.search(r"\d", said))
    told_a_date = trusted or bool(_DATE.search(said))
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

        if change.op == "add_skill_item" and not change.target.strip():
            refused.append(
                f'Did not add anything to "{change.line}": no item was named. '
                "The item goes in target."
            )
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

        # Same bargain as years: the neighbouring entries carry dates, and the
        # model copies one when nobody gave it. A date is a claim about when.
        if change.last_used and not told_a_date:
            refused.append(
                f'Dropped the date on "{change.target}". You did not say when you '
                "last used it, and a date nobody gave is one you have to defend."
            )
            change = change.model_copy(update={"last_used": ""})

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
    """Body bounds of a section. End stops before trailing blanks so inserts land
    before the separator."""
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
    """Rewrite one Skill Evidence entry in place, leaving other lines untouched."""
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

    # Merge field by field so correcting one field keeps the others.
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
    """Add an item to a Skills row; the `items: [...]` list may span several lines."""
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
    """Append a bullet to a project's `bullets:` block. The id is generated here so
    it cannot collide."""
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
    # Quote when there is a colon, or YAML reads the scalar as a mapping.
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
