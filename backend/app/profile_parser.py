"""The master profile markdown -> Profile.

The document is markdown headings wrapping YAML bodies, so the parser is a
heading split plus yaml.safe_load. No hand-rolled tokenizer.

  # Section        -> a top-level section, and only the known names below
  ## Company       -> an Experience entry
  ### Project      -> a Project inside that company

Every failure raises ProfileError carrying the line in the file the person
actually typed, because "line 62" is a fix and "mapping values are not allowed
here" is a puzzle.
"""

import difflib
import re
from pathlib import Path

import yaml
from pydantic import ValidationError

from .models import Profile, ProfileIssue, ProfileSummary, ValidationResult

# The order is the emit order later, so it is the order the file should be
# written in. "skill evidence" is two words because that is what the person
# types; it becomes skill_evidence on the way into the model.
SECTIONS = (
    "meta",
    "identity",
    "titles",
    "summaries",
    "skills",
    "skill evidence",
    "experience",
    "projects",
    "education",
    "certifications",
    "publications",
    "awards",
    "languages",
    "availability",
    "gaps",
    "rules",
)

# Keyed by the normalized name. meta, availability and rules are mappings.
_LIST_SECTIONS = (
    "titles",
    "summaries",
    "skills",
    "skill_evidence",
    "education",
    "certifications",
    "publications",
    "awards",
    "languages",
    "gaps",
)


class ProfileError(Exception):
    """
    A parse failure, with the file line that caused it when there is one.

    `more` carries the rest when one parse produced several independent faults.
    YAML itself is fail-fast, but the schema check is not: it sees every bad
    field at once, and making someone fix six of them one save at a time is the
    whole complaint this exists to answer.
    """

    def __init__(
        self,
        message: str,
        line: int | None = None,
        more: "list[tuple[str, int | None]] | None" = None,
    ):
        super().__init__(message)
        self.message = message
        self.line = line
        self.more = more or []


def parse(path: Path) -> Profile:
    """Convenience for tests and fixtures. The app parses a database row."""
    return parse_text(path.read_text(encoding="utf-8"))


def parse_text(text: str) -> Profile:
    lines = _normalize(text).split("\n")
    chunks, rejected = _chunks(lines, 0, level=1, accept=set(SECTIONS))
    _check_misspelled(rejected)

    sections: dict[str, tuple[str, int]] = {}
    for title, body, start in chunks:
        name = title.strip().lower()
        if name in sections:
            raise ProfileError(f'"# {title}" appears twice. Merge the two into one.', start - 1)
        sections[name] = (body, start)

    if "identity" not in sections:
        raise ProfileError('No "# Identity" section. Every profile needs one.')

    data: dict = {}
    for name in SECTIONS:
        # Both of these hold headings rather than YAML, and are chunked below.
        if name in ("experience", "projects"):
            continue
        key = name.replace(" ", "_")
        body, start = sections.get(name, ("", 1))
        loaded = _yaml(body, start, f"# {name.title()}")
        # A section that holds a list must not silently accept a mapping: it
        # would parse and then come back empty, which reads as "I wrote nothing".
        if key in _LIST_SECTIONS and loaded and not isinstance(loaded, list):
            raise ProfileError(
                f'"# {name.title()}" must be a list. Start each entry with "- ".', start
            )
        data[key] = loaded or ([] if key in _LIST_SECTIONS else {})

    body, start = sections.get("experience", ("", 1))
    companies, _ = _chunks(body.split("\n"), start - 1, level=2)
    data["experience"] = [_company(name, body, at) for name, body, at in companies]

    # Projects holds ### headings with no ## parent, so it chunks one level down
    # and lands in its own list. A synthetic employer to hang them off would be
    # a company that does not exist showing up on a CV.
    body, start = sections.get("projects", ("", 1))
    loose, _ = _chunks(body.split("\n"), start - 1, level=3)
    data["projects"] = [_project(name, body, at) for name, body, at in loose]

    try:
        return Profile.model_validate(data)
    except ValidationError as error:
        first, *rest = _readable(error, lines)
        raise ProfileError(first[0], first[1], rest) from error


def _company(name: str, body: str, start: int) -> dict:
    lines = body.split("\n")
    projects, _ = _chunks(lines, start - 1, level=3)
    # Everything above the first ### belongs to the company itself.
    head = lines[: (projects[0][2] - start - 1) if projects else len(lines)]
    return {
        **_yaml("\n".join(head), start, f"## {name.strip()}"),
        "name": name.strip(),
        "projects": [_project(n, b, at) for n, b, at in projects],
    }


def _project(name: str, body: str, start: int) -> dict:
    name = name.strip()
    # An explicit `id:` in the body wins over the slugged heading.
    return {"id": _slug(name), "name": name, **_yaml(body, start, f"### {name}")}


def _normalize(text: str) -> str:
    # A BOM makes the first "# Identity" invisible to the heading match, and CRLF
    # leaves a \r on every parsed value. Both come free with a Windows editor.
    text = text.lstrip("﻿").replace("\r\n", "\n").replace("\r", "\n")
    # A column-zero "---" reads as a rule between sections in markdown and as a
    # document separator in YAML, and safe_load refuses a stream holding two
    # documents. Without this every section around one fails with "expected a
    # single document in the stream", which says nothing about the horizontal
    # rule that caused it. Blanked, not dropped: errors carry a line number.
    text = re.sub(r"(?m)^---[ \t]*$", "", text)
    # Same treatment for a code fence. The briefing asks Claude to return the
    # file in a markdown code block, so the fence arrives pasted along with the
    # contents often enough, and safe_load's answer to it is "found character
    # '`' that cannot start any token", which helps nobody.
    return re.sub(r"(?m)^ {0,3}```[A-Za-z0-9_-]*[ \t]*$", "", text)


def _chunks(
    lines: list[str], offset: int, level: int, accept: set[str] | None = None
) -> tuple[list[tuple[str, str, int]], list[tuple[str, int]]]:
    """
    Split on headings of exactly `level`, returning (title, body, body_start_line)
    plus the headings that were not accepted.

    `offset` is the file line number of lines[0] minus one, so every line number
    that comes out of here points into the file the person typed.

    Headings the caller does not accept stay in the body on purpose: "# TODO fix
    this" at column zero is a YAML comment, and promoting it to a section would
    silently orphan everything under it.
    """
    heading = re.compile(rf"^#{{{level}}} +(.+?)\s*$")
    marks: list[tuple[int, str]] = []
    rejected: list[tuple[str, int]] = []

    for i, line in enumerate(lines):
        match = heading.match(line)
        if not match:
            continue
        title = match.group(1)
        if accept is not None and title.strip().lower() not in accept:
            rejected.append((title, offset + i + 1))
            continue
        marks.append((i, title))

    chunks = []
    for n, (i, title) in enumerate(marks):
        end = marks[n + 1][0] if n + 1 < len(marks) else len(lines)
        chunks.append((title, "\n".join(lines[i + 1 : end]), offset + i + 2))
    return chunks, rejected


def _check_misspelled(rejected: list[tuple[str, int]]) -> None:
    """
    "# Experiance" would otherwise be treated as a YAML comment and the entire
    work history would vanish without a word. A near miss is a typo, not a note.
    """
    for title, line in rejected:
        near = difflib.get_close_matches(title.strip().lower(), SECTIONS, n=1, cutoff=0.75)
        if near:
            raise ProfileError(
                f'Unknown section "# {title}". Did you mean "# {near[0].title()}"?', line
            )


def _yaml(text: str, start: int, what: str):
    try:
        return yaml.safe_load(text) or {}
    except yaml.YAMLError as error:
        mark = getattr(error, "problem_mark", None)
        problem = getattr(error, "problem", None) or str(error)
        # mark.line is zero-based within this section; start is the file line of
        # the section's first body line.
        raise ProfileError(
            f"{what} is not valid YAML: {problem}.",
            start + mark.line if mark else None,
        ) from error


def _readable(error: ValidationError, lines: list[str]) -> list[tuple[str, int | None]]:
    """
    Pydantic reports a path and a type. A person editing markdown needs the line
    and the fix, so each error is matched back to the text that produced it.
    """
    issues: list[tuple[str, int | None]] = []
    seen: set[tuple[str, int | None]] = set()
    for fault in error.errors():
        issue = _explain(fault, lines)
        if issue not in seen:
            seen.add(issue)
            issues.append(issue)
    if len(issues) > MAX_ERRORS:
        hidden = len(issues) - MAX_ERRORS
        issues = issues[:MAX_ERRORS]
        issues.append((f"and {hidden} more. Fix these first and check again.", None))
    return issues


def _explain(fault: dict, lines: list[str]) -> tuple[str, int | None]:
    where = _where(fault["loc"])
    value = fault.get("input")

    # The colon trap, which is the one people actually hit. "- Built the flow:
    # with OTP" is a mapping to YAML, so the item arrives as a dict and the
    # schema rejects it with a type error that names nothing useful.
    if isinstance(value, dict) and len(value) == 1 and "str" in fault.get("type", ""):
        key = next(iter(value))
        line = _line_of(f"{key}:", lines)
        if line:
            return (
                "This list item has a colon in it, so YAML read it as a name and "
                "a value instead of a sentence. Wrap the whole thing in single "
                f"quotes: {_quoted(lines[line - 1])}",
                line,
            )

    return f"{where}: {fault['msg']}.", _line_of(str(value), lines)


def _where(loc: tuple) -> str:
    """experience -> item 1 -> projects -> item 1 -> claim_boundary -> can_claim -> item 2"""
    return " -> ".join(f"item {p + 1}" if isinstance(p, int) else str(p) for p in loc)


def _line_of(needle: str, lines: list[str]) -> int | None:
    """
    ponytail: first line containing the text, not a real source map. Building
    one means a YAML loader that records marks per node, which is a lot of
    machinery for a number that is right whenever the text appears once.
    """
    if not needle or len(needle) < 3:
        return None
    for index, line in enumerate(lines):
        if needle in line:
            return index + 1
    return None


def _quoted(line: str) -> str:
    """The same list item, quoted, ready to paste over the broken one."""
    body = line.strip().removeprefix("- ").strip().strip("'\"")
    return "- '" + body.replace("'", "''") + "'"


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


# Documented in the template as "one of", so a value outside the set is a typo
# rather than a preference. Warnings, never errors: an unknown value still saves,
# and the generator is what will eventually need to trust these.
LEVELS = ("familiar", "working", "advanced", "expert")
CONTEXTS = ("professional", "personal", "academic")
METRIC_SOURCES = ("measured", "estimated", "reported", "none")
PROJECT_STATUS = ("live", "shipped", "internal", "pilot", "sunset", "abandoned")
EMPLOYMENT = ("full-time", "part-time", "contract", "freelance", "internship", "volunteer")
CERT_STATUS = ("earned", "in_progress", "expired")
PUB_TYPES = ("talk", "article", "paper", "patent", "book", "podcast")
LANG_LEVELS = ("native", "fluent", "professional", "conversational", "basic")
GAP_STATUS = ("none", "learning", "personal-only", "rusty")

# Past this the list stops being read, so the tail is collapsed into a count.
# A hundred warnings and none are the same thing to the person looking at them.
MAX_WARNINGS = 20

# Errors are rarer and each one blocks the save, so the list is shorter.
MAX_ERRORS = 8

DASHES = {"\u2014": "em dash", "\u2013": "en dash"}

# A digit that follows a letter is part of a name, not a measurement: Auth0,
# HTML5, ES6, S3. Asking for a metric block on "Auth0" trains the reader to
# ignore the warning, which is worse than not having it.
_NUMBER = re.compile(r"(?<![A-Za-z])\d")


def replace_bullet_text(source: str, bullet_id: str, text: str) -> str:
    """
    Rewrite one bullet's text in the markdown, leaving the rest of the file byte
    for byte alone.

    Surgery rather than a round trip on purpose. Parsing to a Profile and dumping
    it back would reformat the whole document and drop every comment in it, and
    those comments are half of why the file is readable. The cost is that this
    has to understand the file's shape, which is why it lives beside the parser.

    Raises ProfileError when the id is not there, so a stale screen cannot write
    a bullet into a file that no longer has one.
    """
    lines = source.split("\n")
    item = re.compile(r"^(\s*)-\s+id:\s*(\S+)\s*$")

    start = indent = None
    for number, line in enumerate(lines):
        found = item.match(line)
        if found and found.group(2) == bullet_id:
            if start is not None:
                raise ProfileError(f'Bullet "{bullet_id}" appears twice. Ids have to be unique.')
            start, indent = number, len(found.group(1))
    if start is None:
        raise ProfileError(f'No bullet with id "{bullet_id}" in this profile.')

    # The keys of this bullet sit two columns in from its dash.
    keys = " " * (indent + 2)
    end = len(lines)
    for number in range(start + 1, len(lines)):
        line = lines[number]
        if not line.strip():
            continue
        if len(line) - len(line.lstrip()) <= indent:
            end = number
            break

    for number in range(start + 1, end):
        if not lines[number].startswith(f"{keys}text:"):
            continue
        # The scalar runs on until the next key at this depth.
        last = number
        for follow in range(number + 1, end):
            if lines[follow].strip() and len(lines[follow]) - len(lines[follow].lstrip()) <= len(keys):
                break
            last = follow
        quoted = text.strip().replace("'", "''")
        return "\n".join(lines[: number] + [f"{keys}text: '{quoted}'"] + lines[last + 1 :])

    raise ProfileError(f'Bullet "{bullet_id}" has no text to replace.')


def validate_text(text: str) -> ValidationResult:
    """
    What the editor shows before you are allowed to save.

    ponytail: one error at a time from YAML itself, because a broken document
    cannot be read past the break. The schema check is different: it sees the
    whole parsed file, so every fault it finds is reported together.

    Everything below is a warning. A profile that saved yesterday has to save
    today, because this row is the only copy of the CV data, and refusing it
    over a missing qualifier loses more than it protects. These get promoted to
    errors when a generator exists and there is something to protect.
    """
    try:
        profile = parse_text(text)
    except ProfileError as error:
        return ValidationResult(
            ok=False,
            errors=[
                ProfileIssue(line=error.line, message=error.message),
                *(ProfileIssue(line=line, message=message) for message, line in error.more),
            ],
        )

    warnings: list[ProfileIssue] = []

    def warn(message: str, line: int | None = None) -> None:
        warnings.append(ProfileIssue(line=line, message=message))

    # Employment is not what makes something a project, so every check below
    # runs over both lists.
    projects = profile.all_projects()
    bullets = [bullet for project in projects for bullet in project.bullets]
    missing = [project for project in projects if not _has_boundary(project)]

    # ---------- claims ----------

    if missing:
        warn(
            f"{_count(missing, 'project')} without a claim_boundary "
            f"({_names(missing)}). The guard cannot protect what has no boundary."
        )
    unprotected = [
        project
        for project in projects
        if project.bullets and not project.claim_boundary.cannot_claim
    ]
    if unprotected:
        warn(
            f"{_count(unprotected, 'project')} with bullets but an empty cannot_claim "
            f"({_names(unprotected)}). cannot_claim is the half that protects you: "
            "can_claim only says what may be printed."
        )
    if not projects:
        warn("No projects yet, so there is nothing to select from.")

    # ---------- numbers ----------

    for bullet in bullets:
        if _NUMBER.search(bullet.text) and bullet.metric is None:
            warn(
                f'Bullet "{bullet.id}" quotes a number with no metric block. A number '
                "needs a source you can name out loud, or it becomes one you invented."
            )
        if bullet.metric and bullet.metric.source == "estimated":
            if "estimated" not in bullet.text.lower():
                warn(
                    f'Bullet "{bullet.id}" is an estimate, but the text does not say so. '
                    "The qualifier has to travel with the claim, because the bullet is "
                    "what gets read and the metric block is not."
                )

    # ---------- blocked bullets ----------

    for bullet in bullets:
        if bullet.status != "blocked":
            continue
        if not bullet.blocked_reason:
            warn(
                f'Bullet "{bullet.id}" is blocked with no blocked_reason. Nobody can act '
                "on it later, including you in a month."
            )
        if not bullet.text.strip():
            warn(
                f'Bullet "{bullet.id}" is blocked and empty. Writing the claim out is the '
                "point: an empty one cannot be unblocked because there is nothing to check."
            )

    # ---------- wording ----------

    for number, line in enumerate(_normalize(text).split("\n"), start=1):
        for character, name in DASHES.items():
            if character in line:
                warn(
                    f"An {name} on this line. Rewrite it as a comma, a colon or a full stop.",
                    number,
                )

    banned = [word for word in profile.rules.banned_words if word.strip()]
    for bullet in bullets:
        lowered = bullet.text.lower()
        for word in banned:
            if word.lower() in lowered:
                warn(f'Bullet "{bullet.id}" uses a banned word: "{word}".')

    # ---------- skill evidence ----------

    listed = {
        item.lower()
        for row in profile.skills
        for item in row.items + row.never_standalone + row.gated
    }
    ids = {project.id for project in projects}
    for skill in profile.skill_evidence:
        if skill.name.lower() not in listed:
            warn(
                f'Skill evidence for "{skill.name}", which is in no Skills row. Probably a '
                "typo; nothing will ever match it."
            )
        if skill.gated and not skill.evidence:
            warn(
                f'"{skill.name}" is gated with no evidence, so the gate can never open and '
                "the skill will never print."
            )
        for reference in skill.evidence:
            if reference not in ids:
                warn(
                    f'"{skill.name}" points at project "{reference}", which does not exist. '
                    "Stale reference, usually left behind by a rename."
                )

    # ---------- enums ----------

    for where, value, allowed in _enum_values(profile, projects, bullets):
        if value and value not in allowed:
            warn(f'{where} is "{value}". One of: {", ".join(allowed)}.')

    # ---------- order and coverage ----------

    dated = [employer for employer in profile.experience if employer.start]
    out_of_order = [
        later.name
        for earlier, later in zip(dated, dated[1:])
        if earlier.start < later.start
    ]
    if out_of_order:
        warn(
            f"Employers are not newest first ({', '.join(out_of_order[:3])}). They print in "
            "the order they are written, so this will surprise you on the page."
        )

    if not profile.gaps:
        warn(
            "No Gaps section filled in. Without it, fit scoring has nothing to score "
            "against and degrades to guessing."
        )

    for summary in profile.summaries:
        if len(summary.text) > summary.max_chars:
            warn(
                f'Summary "{summary.id}" is {len(summary.text)} characters, over its '
                f"limit of {summary.max_chars}. It will not fit the layout."
            )

    if len(warnings) > MAX_WARNINGS:
        hidden = len(warnings) - MAX_WARNINGS
        warnings = warnings[:MAX_WARNINGS] + [
            ProfileIssue(message=f"and {hidden} more, hidden so this list stays readable.")
        ]

    return ValidationResult(
        ok=True,
        warnings=warnings,
        summary=ProfileSummary(
            # projects is what sits under an employer; projects_total counts the
            # standalone ones too.
            projects=sum(len(employer.projects) for employer in profile.experience),
            projects_total=len(projects),
            bullets=len(bullets),
            blocked=sum(1 for bullet in bullets if bullet.status == "blocked"),
            missing_boundaries=len(missing),
            skills_evidenced=len(profile.skill_evidence),
            gaps=len(profile.gaps),
            unverified=sum(len(project.unverified) for project in projects),
        ),
    )


def _enum_values(profile, projects, bullets) -> list[tuple[str, str, tuple[str, ...]]]:
    """Everything the template documents as "one of", flattened for one loop."""
    return [
        *((f'Skill evidence "{s.name}" level', s.level, LEVELS) for s in profile.skill_evidence),
        *(
            (f'Skill evidence "{s.name}" context', s.context, CONTEXTS)
            for s in profile.skill_evidence
        ),
        *((f'Project "{p.name}" status', p.status, PROJECT_STATUS) for p in projects),
        *(
            (f'Employer "{e.name}" employment_type', e.employment_type, EMPLOYMENT)
            for e in profile.experience
        ),
        *(
            (f'Certification "{c.name}" status', c.status, CERT_STATUS)
            for c in profile.certifications
        ),
        *((f'Publication "{p.title}" type', p.type, PUB_TYPES) for p in profile.publications),
        *(
            (f'Language "{lang.name}" level', lang.level, LANG_LEVELS)
            for lang in profile.languages
        ),
        *((f'Gap "{g.skill}" status', g.status, GAP_STATUS) for g in profile.gaps),
        *(
            (f'Bullet "{b.id}" metric source', b.metric.source, METRIC_SOURCES)
            for b in bullets
            if b.metric
        ),
    ]


def _count(items: list, noun: str) -> str:
    return f"{len(items)} {noun}{'' if len(items) == 1 else 's'}"


def _names(projects: list) -> str:
    shown = ", ".join(project.name for project in projects[:3])
    return shown if len(projects) <= 3 else f"{shown}, ..."


def _has_boundary(project) -> bool:
    boundary = project.claim_boundary
    return bool(
        boundary.can_claim or boundary.cannot_claim or boundary.required_qualifiers
    )
