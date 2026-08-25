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
    cv, flags = _assemble(profile, answer, body.title_variant, body.parsed_jd)
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


# ---------- assembly, and the guard ----------


def _assemble(
    profile: Profile, answer: dict, forced: str | None, jd: ParsedJd
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


def _coverage(jd: ParsedJd, answer: dict, sections: list[CvSection]) -> list[SkillCoverage]:
    """
    What the page backs, as the selector judged it, minus anything it got wrong.

    Same bargain as the rest of this file: the model points at ids and plain code
    decides whether they mean anything. An id that did not print is dropped, and
    a skill the posting never asked for is not carried through at all, so the
    list is always exactly the posting's requirements in the posting's order.

    ponytail: bullets added afterwards by the page-fill loop are not in the
    model's answer, so they back nothing here. They were picked for length, not
    relevance, so under-crediting them is the safe direction.
    """
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


# What "a full page" means. Under MIN the page reads as a thin candidate and
# gets topped up; over MAX it is two pages pretending to be one. A CV that
# lands between them is left alone.
MIN_FILL = 0.90
MAX_FILL = 1.25


def _fill_page(profile, title, summary, sections, projects, rules, flags) -> None:
    """
    Top the page up until it is actually full, measuring rather than guessing.

    The model decides what is relevant; how much fits is arithmetic, and asking
    a model to do arithmetic it cannot see the result of is how the page ended
    up half empty. Bullets are added in profile priority order from the projects
    already chosen first, then from the next-best unused project.

    ponytail: no second model call. The ordering of the top-ups is the author's
    own priority field rather than relevance to this posting, which is the right
    trade at the bottom of a page. It becomes a second call the day the tail of
    the page matters as much as the top.
    """
    def build() -> GeneratedCv:
        return GeneratedCv(
            title=title.text if title else "",
            summary=summary.text if summary else "",
            skills_lines=_skills(profile, {s.project_id for s in sections}),
            sections=sections,
        )

    # Everything not on the page yet, best first: unused bullets from projects
    # already printing, then the projects that were left out, by priority.
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
                # Look the section up rather than remembering one: the second
                # bullet of a project added a moment ago belongs in the section
                # that bullet created, not in a duplicate of it.
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
                # One bullet that turns a full page into two is worse than the
                # gap it filled, so it goes back.
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
        # No browser, no measurement. The CV is still correct, just unchecked
        # for length, and refusing to generate over that would be worse.
        flags.append(
            Flag(type="warn", message=f"Could not measure the page length. {error}")
        )


def _target(rules) -> str:
    """
    Roughly how many bullets fill one page at this template's size, as a range.

    ponytail: derived from the caps rather than configured, because it is one
    more number to keep in sync for a value nobody would set differently. It
    becomes a Rules field the day the page limit is not one.
    """
    most = rules.max_projects * rules.max_bullets_per_project
    return f"{max(6, most // 2)} to {max(8, int(most * 0.7))}"


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
    # Bullets a re-export could not find in the profile any more. Silently
    # shipping a shorter CV than the one on record is how a re-export came back
    # half a page and nobody knew why.
    dropped: list[str] = []
    id: int
    filename: str
    page_count: int


class PreviewRequest(BaseModel):
    cv: GeneratedCv


@router.post("/preview", response_class=HTMLResponse)
def preview(body: PreviewRequest, session: SessionDep) -> str:
    """
    The page as HTML, for the preview pane to show in an iframe.

    The same render_html the PDF goes through, so the preview cannot drift from
    the printed artefact: there is one template and this is it. The hand-written
    approximation this replaced had stopped matching the moment cv.html changed,
    which is the failure any second renderer eventually has.
    """
    source = session.exec(select(ProfileSource)).first()
    if source is None:
        raise HTTPException(404, "No profile saved yet.")
    return render_html(parse_text(source.text), body.cv)


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
    row.coverage = [item.model_dump() for item in body.cv.coverage]
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
                    named=project.named,
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
    return ExportResponse(id=row.id, filename=row.filename, page_count=pages, dropped=missing)
