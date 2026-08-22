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

SECTIONS = (
    "identity",
    "titles",
    "summaries",
    "skills",
    "experience",
    "education",
    "certifications",
    "languages",
)

_LIST_SECTIONS = ("titles", "summaries", "skills", "education", "certifications", "languages")


class ProfileError(Exception):
    """A parse failure, with the file line that caused it when there is one."""

    def __init__(self, message: str, line: int | None = None):
        super().__init__(message)
        self.message = message
        self.line = line


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
        if name == "experience":
            continue
        body, start = sections.get(name, ("", 1))
        loaded = _yaml(body, start, f"# {name.title()}")
        # A section that holds a list must not silently accept a mapping: it
        # would parse and then come back empty, which reads as "I wrote nothing".
        if name in _LIST_SECTIONS and loaded and not isinstance(loaded, list):
            raise ProfileError(
                f'"# {name.title()}" must be a list. Start each entry with "- ".', start
            )
        data[name] = loaded or ([] if name in _LIST_SECTIONS else {})

    body, start = sections.get("experience", ("", 1))
    companies, _ = _chunks(body.split("\n"), start - 1, level=2)
    data["experience"] = [_company(name, body, at) for name, body, at in companies]

    try:
        return Profile.model_validate(data)
    except ValidationError as error:
        raise ProfileError(_readable(error)) from error


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
    return text.lstrip("﻿").replace("\r\n", "\n").replace("\r", "\n")


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


def _readable(error: ValidationError) -> str:
    first = error.errors()[0]
    where = " -> ".join(str(p) for p in first["loc"])
    return f"{where}: {first['msg']}" if where else first["msg"]


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def validate_text(text: str) -> ValidationResult:
    """
    What the editor shows before you are allowed to save.

    ponytail: one error at a time. The parser is fail-fast because YAML is, and
    collecting more would mean re-parsing after each guessed fix. Warnings are
    the things worth knowing that are not reasons to refuse the file.
    """
    try:
        profile = parse_text(text)
    except ProfileError as error:
        return ValidationResult(
            ok=False, errors=[ProfileIssue(line=error.line, message=error.message)]
        )

    projects = [project for exp in profile.experience for project in exp.projects]
    bullets = [bullet for project in projects for bullet in project.bullets]
    missing = [project for project in projects if not _has_boundary(project)]
    warnings: list[ProfileIssue] = []

    if missing:
        names = ", ".join(project.name for project in missing[:3])
        warnings.append(
            ProfileIssue(
                message=f"{len(missing)} project{'' if len(missing) == 1 else 's'} without a "
                f"claim_boundary ({names}). The guard cannot protect what has no boundary."
            )
        )
    if not projects:
        warnings.append(
            ProfileIssue(message="No projects yet, so there is nothing to select from.")
        )
    for summary in profile.summaries:
        if len(summary.text) > summary.max_chars:
            warnings.append(
                ProfileIssue(
                    message=f'Summary "{summary.id}" is {len(summary.text)} characters, over its '
                    f"limit of {summary.max_chars}. It will not fit the layout."
                )
            )

    return ValidationResult(
        ok=True,
        warnings=warnings,
        summary=ProfileSummary(
            projects=len(projects),
            bullets=len(bullets),
            blocked=sum(1 for bullet in bullets if bullet.status == "blocked"),
            missing_boundaries=len(missing),
        ),
    )


def _has_boundary(project) -> bool:
    boundary = project.claim_boundary
    return bool(
        boundary.can_claim or boundary.cannot_claim or boundary.required_qualifiers
    )
