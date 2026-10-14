"""CV generation: the model picks bullet ids from the profile, plain code checks
the pick and fills the page, then preview and PDF export."""

import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
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
    SkillCoverage,
    SkillsLine,
)
from .profile_parser import parse_text
from .render import filename, measurer, render_html, to_pdf
from .tables import Application, ProfileSource, current_profile

router = APIRouter(tags=["generate"])


class GenerateRequest(BaseModel):
    jd_text: str
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
        "coverage": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "skill": {"type": "string"},
                    "bullet_ids": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["skill", "bullet_ids"],
            },
        },
    },
    "required": ["title_id", "sections", "coverage"],
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

Fill the page. It is one page and it should be a full one, roughly {target}
bullets in total across the projects you choose. Under-filling is the failure
this gets wrong most often: half a page of white space reads as a thin
candidate, not a focused one. If a project is relevant, give it the evidence it
deserves rather than a single line.

Rules:

- Only ids that appear in the pool below. An id you cannot find is a mistake,
  not a suggestion.
- Never pick a blocked bullet. They are excluded from the pool already; if one
  reaches you, it is still not eligible.
- Prefer a bullet that evidences something the posting explicitly requires over
  one that is merely impressive.
- Required skills decide whether a project belongs on the page. Preferred skills
  decide which of the close ones wins. When two projects back the requirements
  about equally, take the one that also evidences something from the preferred
  list: every applicant has the required list, which is why the posting bothered
  to write the other one. Preferred never outranks required, and never carries a
  project that fails the requirements.
- A project whose cannot_claim excludes what the posting is asking for is weak
  evidence for that requirement, however good the bullets read.
- Leave a project out entirely rather than padding it with a bullet that says
  nothing about this posting. Relevance decides what goes on, and the target
  above decides how much: never both at once, and never padding to reach it.
- Do not pick a project only because it is recent.

Then say what the page backs. For every skill in WHAT THE POSTING ASKS FOR,
required and preferred alike, return one coverage entry: the skill name copied
exactly as the posting listed it, and the ids of the bullets you selected that
the person could point at if an interviewer asked about that skill.

- Judge it by meaning, not by wording. A bullet about shipping a React Native
  app to both stores backs "mobile app development" without using the phrase,
  and a bullet naming GitHub Actions backs "CI/CD".
- Only ids you actually selected above. A bullet that is not on the page cannot
  back anything, however well it would have.
- Return an empty list when nothing you picked backs it, and do not stretch to
  avoid one. The empty lists are the point of this field: they are what tells
  the person the posting asks for something their page does not show.
- One entry per skill, and every skill gets one."""


@router.post("/generate")
def generate(body: GenerateRequest, session: SessionDep) -> GenerateResponse:
    text = (body.jd_text or "").strip()
    if len(text) < 80:
        raise HTTPException(422, "That is too short to select against.")

    row = current_profile(session)
    if row is None:
        raise HTTPException(404, "No profile saved yet. There is nothing to select from.")
    profile = parse_text(row.text)

    pool = {bullet.id: bullet for bullet in _pool(profile)}
    if not pool:
        raise HTTPException(
            422, "Every bullet in your profile is blocked, so there is nothing to print."
        )

    answer = generate_json(_prompt(profile, text, body), SCHEMA)
    cv, flags = _assemble(profile, answer, body.title_variant, body.parsed_jd)
    return GenerateResponse(cv=cv, flags=flags)


def _pool(profile: Profile) -> list[Bullet]:
    """Bullets the model may pick from. Blocked ones are left out entirely."""
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
        max_projects=rules.max_projects,
        max_bullets=rules.max_bullets_per_project,
        target=_target(rules),
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


def _assemble(
    profile: Profile, answer: dict, forced: str | None, jd: ParsedJd
) -> tuple[GeneratedCv, list[Flag]]:
    flags: list[Flag] = []
    projects = {project.id: project for project in profile.all_projects()}
    rules = profile.rules

    title_id = forced or str(answer.get("title_id") or "")
    title = next((t for t in profile.titles if t.id == title_id), None)
    if title is None:
        # The profile names its own fallback ("Default when nothing else fits").
        # File order picked "mobile" for a React web posting.
        title = next(
            (t for t in profile.titles if "default" in t.use_when.casefold()),
            profile.titles[0] if profile.titles else None,
        )
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
                    named=project.named,
                    bullets=bullets,
                )
            )

    _fill_page(profile, title, summary, sections, projects, rules, flags)

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
        coverage=_coverage(jd, answer, sections),
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
            # Never in the pool, so this id came from somewhere else. Refuse it.
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


def _coverage(jd: ParsedJd, answer: dict, sections: list[CvSection]) -> list[SkillCoverage]:
    """The model's coverage claims, limited to bullets that printed.
    Bullets added by the fill loop back nothing, on purpose."""
    printed = {bullet.id for section in sections for bullet in section.bullets}
    claimed: dict[str, list[str]] = {}
    for entry in answer.get("coverage") or []:
        name = str(entry.get("skill") or "").strip().casefold()
        if name:
            claimed[name] = [str(i) for i in entry.get("bullet_ids") or []]
    return [
        SkillCoverage(
            skill=skill.name,
            bullet_ids=[
                i for i in claimed.get(skill.name.strip().casefold(), []) if i in printed
            ],
        )
        for skill in [*jd.required_skills, *jd.preferred_skills]
    ]


def _check_qualifiers(sections, projects, printed: str, flags: list[Flag]) -> None:
    """Warn when a project's required qualifier is missing from the printed page."""
    lowered = printed.lower()
    for section in sections:
        project = projects[section.project_id]
        for qualifier in project.claim_boundary.required_qualifiers:
            # Keyword overlap, since the qualifier rarely appears word for word.
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


# Below MIN_FILL the page gets topped up; a bullet that pushes it past MAX_FILL is undone.
MIN_FILL = 0.90
MAX_FILL = 1.25


def _fill_page(profile, title, summary, sections, projects, rules, flags) -> None:
    """Add unused bullets in priority order until the page is full, measured in Chromium."""
    def build() -> GeneratedCv:
        return GeneratedCv(
            title=title.text if title else "",
            summary=summary.text if summary else "",
            skills_lines=_skills(profile, {s.project_id for s in sections}),
            sections=sections,
        )

    on_page = {b.source_id for s in sections for b in s.bullets}
    chosen = [projects[s.project_id] for s in sections]
    rest = sorted(
        (p for p in profile.all_projects() if p.id not in {c.id for c in chosen}),
        key=lambda p: p.priority,
    )
    spare: list[tuple[Project, Bullet]] = [
        (project, bullet)
        for project in chosen + rest
        for bullet in sorted(project.bullets, key=lambda b: b.priority)
        if bullet.id not in on_page and bullet.status != "blocked"
    ]

    try:
        with measurer() as pages:
            filled = started = pages(render_html(profile, build()))
            added = 0
            while filled < MIN_FILL and spare:
                project, bullet = spare.pop(0)
                # Look the section up each time so a second bullet doesn't start a duplicate.
                section = next((s for s in sections if s.project_id == project.id), None)
                fresh = section is None
                if fresh:
                    if len(sections) >= rules.max_projects:
                        continue
                    section = CvSection(
                        project_id=project.id,
                        project_name=project.name,
                        label=project.label,
                        stack=project.stack,
                        named=project.named,
                    )
                    sections.append(section)
                elif len(section.bullets) >= rules.max_bullets_per_project:
                    continue
                section.bullets.append(
                    SelectedBullet(id=bullet.id, source_id=bullet.id, text=bullet.text)
                )
                grown = pages(render_html(profile, build()))
                # A bullet that turns one page into two is worse than the gap.
                if grown > MAX_FILL:
                    section.bullets.pop()
                    if fresh:
                        sections.remove(section)
                    break
                filled, added = grown, added + 1

            if added:
                flags.append(
                    Flag(
                        type="warn",
                        message=f"Added {added} more bullet{'s' if added > 1 else ''} to fill the "
                        f"page: the selector came back at {started:.2f} of a page, now "
                        f"{filled:.2f}. "
                        "They are in your own priority order, so check the tail reads right.",
                    )
                )
            elif filled < MIN_FILL:
                flags.append(
                    Flag(
                        type="warn",
                        message=f"This comes to {filled:.2f} of a page and there is nothing "
                        "unused left to add. Write more bullets, or accept a short CV.",
                    )
                )
    except Exception as error:  # noqa: BLE001
        # Without a browser the CV is still valid, just unmeasured, so warn instead of failing.
        flags.append(
            Flag(type="warn", message=f"Could not measure the page length. {error}")
        )


def _target(rules) -> str:
    """Target bullet count for the prompt, derived from the caps."""
    most = rules.max_projects * rules.max_bullets_per_project
    return f"{max(6, most // 2)} to {max(8, int(most * 0.7))}"


def _skills(profile: Profile, selected: set[str]) -> list[SkillsLine]:
    """Gated skills print only when a project evidencing them is on the page."""
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
    """Turn "U+2014" into the character; anything else passes through."""
    token = raw.strip().upper()
    if token.startswith("U+"):
        try:
            return chr(int(token[2:], 16))
        except ValueError:
            return ""
    return raw


class ExportRequest(BaseModel):
    application_id: int
    cv: GeneratedCv


class ExportResponse(BaseModel):
    # Bullet ids a re-export could not find in the profile.
    dropped: list[str] = []
    id: int
    filename: str
    page_count: int


class PreviewRequest(BaseModel):
    cv: GeneratedCv


@router.post("/preview", response_class=HTMLResponse)
def preview(body: PreviewRequest, session: SessionDep) -> str:
    """Preview HTML, from the same render_html the PDF uses."""
    source = current_profile(session)
    if source is None:
        raise HTTPException(404, "No profile saved yet.")
    return render_html(parse_text(source.text), body.cv)


@router.post("/export")
def export(body: ExportRequest, session: SessionDep) -> ExportResponse:
    row = session.get(Application, body.application_id)
    if row is None:
        raise HTTPException(404, "No such application to attach a CV to.")

    source = current_profile(session)
    if source is None:
        raise HTTPException(404, "No profile saved yet.")
    profile = parse_text(source.text)

    pdf, pages = to_pdf(render_html(profile, body.cv))

    row.pdf = pdf
    row.filename = filename(profile.identity.name, row.company, row.role)
    # Snapshot of what was sent, as printed.
    row.title_variant = body.cv.title
    row.summary_text = body.cv.summary
    row.selected_bullet_ids = [b.id for s in body.cv.sections for b in s.bullets]
    row.selected_bullets = [
        {"id": bullet.id, "text": bullet.text, "project_name": section.project_name}
        for section in body.cv.sections
        for bullet in section.bullets
    ]
    row.coverage = [item.model_dump() for item in body.cv.coverage]
    session.add(row)
    session.commit()
    session.refresh(row)
    return ExportResponse(id=row.id, filename=row.filename, page_count=pages)


# Temporary: rebuilds a stored PDF with the current template, no model call.
# Bullet text comes from the row but labels and skills from today's profile.


class ReexportRequest(BaseModel):
    application_id: int


@router.post("/reexport")
def reexport(body: ReexportRequest, session: SessionDep) -> ExportResponse:
    row = session.get(Application, body.application_id)
    if row is None:
        raise HTTPException(404, "No such application.")
    if not row.selected_bullets:
        raise HTTPException(422, "No CV was ever exported for this one, so there is nothing to rebuild.")

    source = current_profile(session)
    if source is None:
        raise HTTPException(404, "No profile saved yet.")
    profile = parse_text(source.text)

    # Matched on bullet id, not project name, so a rename still resolves.
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
                    named=project.named,
                )
            )
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

    # Only the bytes and the name. A re-render must not rewrite what was sent.
    row.pdf = pdf
    row.filename = filename(profile.identity.name, row.company, row.role)
    session.add(row)
    session.commit()
    session.refresh(row)
    return ExportResponse(id=row.id, filename=row.filename, page_count=pages, dropped=missing)
