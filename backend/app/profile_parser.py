"""Parse and validate the master profile: markdown headings (# section, ## company,
### project) wrapping YAML bodies. Errors carry the source line."""

import difflib
import re
from pathlib import Path

import yaml
from pydantic import ValidationError

from .models import Profile, ProfileIssue, ProfileSummary, ValidationResult

# Also the emit order.
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
    """A parse failure with its file line. `more` holds any further errors."""

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
        if name in ("experience", "projects"):
            continue
        key = name.replace(" ", "_")
        body, start = sections.get(name, ("", 1))
        loaded = _yaml(body, start, f"# {name.title()}")
        # A mapping here would otherwise silently read as empty.
        if key in _LIST_SECTIONS and loaded and not isinstance(loaded, list):
            raise ProfileError(
                f'"# {name.title()}" must be a list. Start each entry with "- ".', start
            )
        data[key] = loaded or ([] if key in _LIST_SECTIONS else {})

    body, start = sections.get("experience", ("", 1))
    companies, _ = _chunks(body.split("\n"), start - 1, level=2)
    data["experience"] = [_company(name, body, at) for name, body, at in companies]

    # ### with no ## parent: kept as loose projects, not under a made-up employer.
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
    return {"id": _slug(name), "name": name, **_yaml(body, start, f"### {name}")}


def _normalize(text: str) -> str:
    # A BOM hides the first heading and CRLF leaves \r on every value.
    text = text.lstrip("﻿").replace("\r\n", "\n").replace("\r", "\n")
    # "---" is a YAML document separator safe_load refuses. Blank it, not drop
    # it, so line numbers stay right.
    text = re.sub(r"(?m)^---[ \t]*$", "", text)
    # Same for pasted code fences.
    return re.sub(r"(?m)^ {0,3}```[A-Za-z0-9_-]*[ \t]*$", "", text)


def _chunks(
    lines: list[str], offset: int, level: int, accept: set[str] | None = None
) -> tuple[list[tuple[str, str, int]], list[tuple[str, int]]]:
    """Split on level-`level` headings into (title, body, start_line), plus rejected
    headings, which stay in the body since "# TODO" is a YAML comment."""
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
    # "# Experiance" would read as a YAML comment and silently drop every job.
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
        # mark.line is zero-based within the section; start is its first line.
        raise ProfileError(
            f"{what} is not valid YAML: {problem}.",
            start + mark.line if mark else None,
        ) from error


def _readable(error: ValidationError, lines: list[str]) -> list[tuple[str, int | None]]:
    """Turn pydantic errors into (message, line) pairs, deduped and capped."""
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

    # The colon trap: "- Built the flow: with OTP" is a mapping to YAML.
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
    return " -> ".join(f"item {p + 1}" if isinstance(p, int) else str(p) for p in loc)


def _line_of(needle: str, lines: list[str]) -> int | None:
    # First line containing the text; a heuristic, not a real source map.
    if not needle or len(needle) < 3:
        return None
    for index, line in enumerate(lines):
        if needle in line:
            return index + 1
    return None


def _quoted(line: str) -> str:
    body = line.strip().removeprefix("- ").strip().strip("'\"")
    return "- '" + body.replace("'", "''") + "'"


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


# Allowed enum values. Anything else is a warning, never an error.
LEVELS = ("familiar", "working", "advanced", "expert")
CONTEXTS = ("professional", "personal", "academic")
METRIC_SOURCES = ("measured", "estimated", "reported", "none")
PROJECT_STATUS = ("live", "shipped", "internal", "pilot", "sunset", "abandoned")
EMPLOYMENT = ("full-time", "part-time", "contract", "freelance", "internship", "volunteer")
CERT_STATUS = ("earned", "in_progress", "expired")
PUB_TYPES = ("talk", "article", "paper", "patent", "book", "podcast")
LANG_LEVELS = ("native", "fluent", "professional", "conversational", "basic")
GAP_STATUS = ("none", "learning", "personal-only", "rusty")

# Past these, the tail collapses into a count.
MAX_WARNINGS = 20

MAX_ERRORS = 8

DASHES = {"\u2014": "em dash", "\u2013": "en dash"}

# A digit after a letter is a name, not a measurement: Auth0, HTML5, S3.
_NUMBER = re.compile(r"(?<![A-Za-z])\d")


def replace_bullet_text(source: str, bullet_id: str, text: str) -> str:
    """Rewrite one bullet's text in place. Not parse-and-dump, which would drop
    comments and formatting."""
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
    """Errors block saving; everything else is a warning shown in the editor."""
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

    projects = profile.all_projects()
    bullets = [bullet for project in projects for bullet in project.bullets]
    missing = [project for project in projects if not _has_boundary(project)]

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

    for where, value, allowed in _enum_values(profile, projects, bullets):
        if value and value not in allowed:
            warn(f'{where} is "{value}". One of: {", ".join(allowed)}.')

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
