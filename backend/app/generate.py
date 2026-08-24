"""
The selector, and the guard that checks it.

The model is handed the bullet pool and asked which ids to print. It returns ids
and nothing else. That is the structural guarantee this whole app rests on: a
model that can only point at existing sentences cannot write a new one. Every
other honesty mechanism here is a policy a model could quietly break; this one
it cannot, because the prose is assembled from the profile after the call.

The guard runs afterwards and is plain code. It checks the things the model
could still get wrong even while obeying the format: pointing at a blocked
bullet, dropping a qualifier that has to travel with a claim, or letting a gated
skill onto the page with nothing evidencing it.
"""

import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlmodel import select

from .db import SessionDep
from .model import generate_json
from .models import (
    Bullet,
    CvSection,
    Flag,
    GeneratedCv,
    ParsedJd,
    Profile,
    Project,
    SelectedBullet,
    SkillsLine,
)
from .profile_parser import parse_text
from .render import filename, render_html, to_pdf
from .tables import Application, ProfileSource

router = APIRouter(tags=["generate"])


class GenerateRequest(BaseModel):
    jd_text: str
    # What the fit check already worked out. Passed back rather than re-derived:
    # reading the posting twice is two chances to disagree with itself.
    parsed_jd: ParsedJd = ParsedJd()
    title_variant: str | None = None


class GenerateResponse(BaseModel):
    cv: GeneratedCv
    flags: list[Flag]


SCHEMA = {
    "type": "object",
    "properties": {
        "title_id": {"type": "string"},
        "sections": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "project_id": {"type": "string"},
                    "bullet_ids": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["project_id", "bullet_ids"],
            },
        },
    },
    "required": ["title_id", "sections"],
}

INSTRUCTIONS = """You are choosing which of a candidate's existing bullets belong on a
one-page CV for one specific posting.

You are not writing anything. You return ids. The words on the page are the ones
already in the profile, and they will be assembled from it after you answer, so
anything you invent here is discarded rather than printed.

What to do:

- Pick the title_id whose use_when best matches the posting.
- Pick the projects worth the page, most relevant first, at most {max_projects}.
- Within each, pick at most {max_bullets} bullet ids, strongest evidence first.
- Order matters. What you put first is what gets read.

Rules:

- Only ids that appear in the pool below. An id you cannot find is a mistake,
  not a suggestion.
- Never pick a blocked bullet. They are excluded from the pool already; if one
  reaches you, it is still not eligible.
- Prefer a bullet that evidences something the posting explicitly requires over
  one that is merely impressive.
- A project whose cannot_claim excludes what the posting is asking for is weak
  evidence for that requirement, however good the bullets read.
- Leave a project out entirely rather than padding it with a bullet that does
  not speak to this posting. A shorter, sharper page wins.
- Do not pick a project only because it is recent."""


@router.post("/generate")
def generate(body: GenerateRequest, session: SessionDep) -> GenerateResponse:
    text = (body.jd_text or "").strip()
    if len(text) < 80:
        raise HTTPException(422, "That is too short to select against.")

    row = session.exec(select(ProfileSource)).first()
    if row is None:
        raise HTTPException(404, "No profile saved yet. There is nothing to select from.")
    profile = parse_text(row.text)

    pool = {bullet.id: bullet for bullet in _pool(profile)}
    if not pool:
        raise HTTPException(
            422, "Every bullet in your profile is blocked, so there is nothing to print."
        )

    answer = generate_json(_prompt(profile, text, body), SCHEMA)
    cv, flags = _assemble(profile, answer, body.title_variant)
    return GenerateResponse(cv=cv, flags=flags)


# ---------- what the model sees ----------


def _pool(profile: Profile) -> list[Bullet]:
    """Blocked bullets never reach the model. Excluded, not merely discouraged."""
    return [
        bullet
        for project in profile.all_projects()
        for bullet in project.bullets
        if bullet.status != "blocked"
    ]


def _prompt(profile: Profile, jd_text: str, body: GenerateRequest) -> str:
    rules = profile.rules
    context = {
        "titles": [{"id": t.id, "text": t.text, "use_when": t.use_when} for t in profile.titles],
        "projects": [
            {
                "id": project.id,
                "name": project.name,
                "label": project.label,
                "stack": project.stack,
                "tags": project.tags,
                "my_role": project.my_role,
                "priority": project.priority,
                "cannot_claim": project.claim_boundary.cannot_claim,
                "bullets": [
                    {
                        "id": bullet.id,
                        "text": bullet.text,
                        "priority": bullet.priority,
                        "tags": bullet.tags,
                    }
                    for bullet in project.bullets
                    if bullet.status != "blocked"
                ],
            }
            for project in profile.all_projects()
            if any(b.status != "blocked" for b in project.bullets)
        ],
    }
    instructions = INSTRUCTIONS.format(
        max_projects=rules.max_projects, max_bullets=rules.max_bullets_per_project
    )
    chosen = (
        f"\n\nThe person has already chosen the framing: use title_id "
        f'"{body.title_variant}".'
        if body.title_variant
        else ""
    )
    return (
        f"{instructions}{chosen}\n\nPOOL:\n{json.dumps(context)}"
        f"\n\nWHAT THE POSTING ASKS FOR:\n{body.parsed_jd.model_dump_json()}"
        f"\n\nPOSTING:\n{jd_text}"
    )


# ---------- assembly, and the guard ----------


def _assemble(
    profile: Profile, answer: dict, forced: str | None
) -> tuple[GeneratedCv, list[Flag]]:
    flags: list[Flag] = []
    projects = {project.id: project for project in profile.all_projects()}
    rules = profile.rules

    title_id = forced or str(answer.get("title_id") or "")
    title = next((t for t in profile.titles if t.id == title_id), None)
    if title is None:
        title = profile.titles[0] if profile.titles else None
        if title_id:
            flags.append(
                Flag(
                    type="warn",
                    message=f'No title called "{title_id}". Fell back to '
                    f'"{title.id if title else "nothing"}".',
                )
            )
    summary = next((s for s in profile.summaries if title and s.id == title.id), None)
    if title and summary is None:
        flags.append(
            Flag(type="warn", message=f'No summary written for the "{title.id}" framing.')
        )

    sections: list[CvSection] = []
    for entry in (answer.get("sections") or [])[: rules.max_projects]:
        project = projects.get(str(entry.get("project_id") or ""))
        if project is None:
            flags.append(
                Flag(
                    type="block",
                    message=f'The selector pointed at project "{entry.get("project_id")}", '
                    "which does not exist. Nothing was invented, but nothing was found either.",
                )
            )
            continue
        bullets = _bullets(project, entry.get("bullet_ids") or [], rules, flags)
        if bullets:
            sections.append(
                CvSection(
                    project_id=project.id,
                    project_name=project.name,
                    label=project.label,
                    stack=project.stack,
                    bullets=bullets,
                )
            )

    printed = " ".join(
        [summary.text if summary else ""]
        + [bullet.text for section in sections for bullet in section.bullets]
    )
    _check_qualifiers(sections, projects, printed, flags)
    _check_banned(rules, printed, flags)

    cv = GeneratedCv(
        title=title.text if title else "",
        summary=summary.text if summary else "",
        skills_lines=_skills(profile, {section.project_id for section in sections}),
        sections=sections,
    )
    if not sections:
        flags.append(Flag(type="block", message="Nothing was selected, so there is no CV."))
    return cv, flags


def _bullets(project: Project, ids: list, rules, flags: list[Flag]) -> list[SelectedBullet]:
    by_id = {bullet.id: bullet for bullet in project.bullets}
    chosen: list[SelectedBullet] = []
    for raw in ids[: rules.max_bullets_per_project]:
        bullet = by_id.get(str(raw))
        if bullet is None:
            flags.append(
                Flag(
                    type="block",
                    message=f'The selector pointed at bullet "{raw}", which is not in '
                    f'"{project.name}". A CV cannot print a claim that does not exist.',
                )
            )
            continue
        if bullet.status == "blocked":
            # It was kept out of the pool, so reaching here means the model
            # produced an id from somewhere else. Refuse it loudly.
            flags.append(
                Flag(
                    type="block",
                    message=f'Bullet "{bullet.id}" is blocked and was selected anyway. '
                    f"{bullet.blocked_reason or 'No reason was recorded.'}",
                )
            )
            continue
        chosen.append(
            SelectedBullet(id=bullet.id, text=bullet.text, source_id=bullet.id, rephrased=False)
        )
    return chosen


def _check_qualifiers(sections, projects, printed: str, flags: list[Flag]) -> None:
    """
    A required qualifier is wording that must travel with the claim every time it
    prints. Checked against what is actually on the page, not against intent.
    """
    lowered = printed.lower()
    for section in sections:
        project = projects[section.project_id]
        for qualifier in project.claim_boundary.required_qualifiers:
            # A whole sentence will not appear verbatim, so the check is on the
            # words that carry it. ponytail: keyword overlap, not entailment.
            # A real check needs the qualifier written as the phrase it requires.
            words = [w for w in _words(qualifier) if len(w) > 4]
            if words and not any(word in lowered for word in words):
                flags.append(
                    Flag(
                        type="warn",
                        message=f'"{project.name}" requires a qualifier that is not on the '
                        f"page: {qualifier}",
                    )
                )


def _check_banned(rules, printed: str, flags: list[Flag]) -> None:
    lowered = printed.lower()
    for word in rules.banned_words:
        if word.strip() and word.lower() in lowered:
            flags.append(
                Flag(type="block", message=f'A banned word reached the page: "{word}".')
            )
    for raw in rules.banned_chars:
        character = _codepoint(raw)
        if character and character in printed:
            flags.append(
                Flag(type="block", message=f"A banned character reached the page: {raw}.")
            )


def _skills(profile: Profile, selected: set[str]) -> list[SkillsLine]:
    """
    Gated skills reach the page only when a project evidencing them is on it.
    That is what "gated" means, and it is checked here rather than trusted to
    the model, because it is a lookup and not a judgement.
    """
    evidenced = {
        skill.name.lower()
        for skill in profile.skill_evidence
        if any(project in selected for project in skill.evidence)
    }
    lines: list[SkillsLine] = []
    for row in profile.skills:
        gated = {item.lower() for item in row.gated}
        items = [
            item for item in row.items if item.lower() not in gated or item.lower() in evidenced
        ]
        # never_standalone earns its place only next to something else.
        alone = {item.lower() for item in row.never_standalone}
        if len(items) == 1 and items[0].lower() in alone:
            items = []
        if items:
            lines.append(SkillsLine(line=row.line, items=items))
    return lines


def _words(text: str) -> list[str]:
    return [part.strip(".,;:()\"'").lower() for part in text.split()]


def _codepoint(raw: str) -> str:
    """Rules writes banned characters as U+2014 so the file holds none of them."""
    token = raw.strip().upper()
    if token.startswith("U+"):
        try:
            return chr(int(token[2:], 16))
        except ValueError:
            return ""
    return raw


# ---------- export ----------


class ExportRequest(BaseModel):
    """
    The CV as the person left it: reordered, with anything they deselected
    already gone. Not re-derived from the selector's answer, because what gets
    printed is what was on screen.
    """

    application_id: int
    cv: GeneratedCv


class ExportResponse(BaseModel):
    id: int
    filename: str
    page_count: int


@router.post("/export")
def export(body: ExportRequest, session: SessionDep) -> ExportResponse:
    row = session.get(Application, body.application_id)
    if row is None:
        raise HTTPException(404, "No such application to attach a CV to.")

    source = session.exec(select(ProfileSource)).first()
    if source is None:
        raise HTTPException(404, "No profile saved yet.")
    profile = parse_text(source.text)

    pdf, pages = to_pdf(render_html(profile, body.cv))

    row.pdf = pdf
    row.filename = filename(profile.identity.name, row.company, row.role)
    # The record of what was actually sent. Stored as printed rather than joined
    # against the profile at read time, because the profile keeps changing and
    # this has to show what the employer read.
    row.title_variant = body.cv.title
    row.summary_text = body.cv.summary
    row.selected_bullet_ids = [b.id for s in body.cv.sections for b in s.bullets]
    row.selected_bullets = [
        {"id": bullet.id, "text": bullet.text, "project_name": section.project_name}
        for section in body.cv.sections
        for bullet in section.bullets
    ]
    session.add(row)
    session.commit()
    session.refresh(row)
    return ExportResponse(id=row.id, filename=row.filename, page_count=pages)


# ---------- TEMPORARY: re-export ----------
#
# ponytail: this exists because the CV template changed after PDFs had already
# been stored, and the stored bytes are the only copy. It rebuilds the page from
# the record on the row rather than asking the model anything.
#
# Delete the route, ReexportRequest, and the button on the detail page together
# once the template has settled. Nothing else depends on it.
#
# The known ceiling: it re-renders with today's profile. The bullet text comes
# off the row, so the words are the ones that were sent, but the employer's
# name, the project labels and the skills block are read from the profile as it
# is now. Edit the profile between exporting and re-exporting and the second PDF
# is not the first one.


class ReexportRequest(BaseModel):
    application_id: int


@router.post("/reexport")
def reexport(body: ReexportRequest, session: SessionDep) -> ExportResponse:
    row = session.get(Application, body.application_id)
    if row is None:
        raise HTTPException(404, "No such application.")
    if not row.selected_bullets:
        raise HTTPException(422, "No CV was ever exported for this one, so there is nothing to rebuild.")

    source = session.exec(select(ProfileSource)).first()
    if source is None:
        raise HTTPException(404, "No profile saved yet.")
    profile = parse_text(source.text)

    # Which project each bullet came from. Matched on the bullet id rather than
    # the project name, because a renamed project still has the same ids.
    owner = {bullet.id: project for project in profile.all_projects() for bullet in project.bullets}

    sections: list[CvSection] = []
    missing: list[str] = []
    for saved in row.selected_bullets:
        project = owner.get(saved.get("id", ""))
        if project is None:
            missing.append(saved.get("id", "?"))
            continue
        if not sections or sections[-1].project_id != project.id:
            sections.append(
                CvSection(
                    project_id=project.id,
                    project_name=project.name,
                    label=project.label,
                    stack=project.stack,
                )
            )
        # The text is the one that was sent, not whatever the profile says today.
        sections[-1].bullets.append(
            SelectedBullet(id=saved["id"], source_id=saved["id"], text=saved["text"])
        )

    if not sections:
        raise HTTPException(
            422,
            "None of the bullets on this application are in the profile any more, "
            f"so there is nothing left to print. Missing: {', '.join(missing)}.",
        )

    cv = GeneratedCv(
        title=row.title_variant or "",
        summary=row.summary_text or "",
        skills_lines=_skills(profile, {section.project_id for section in sections}),
        sections=sections,
    )
    pdf, pages = to_pdf(render_html(profile, cv))

    # Only the bytes and the name. What was sent is already recorded and must not
    # be rewritten by a re-render.
    row.pdf = pdf
    row.filename = filename(profile.identity.name, row.company, row.role)
    session.add(row)
    session.commit()
    session.refresh(row)
    return ExportResponse(id=row.id, filename=row.filename, page_count=pages)
