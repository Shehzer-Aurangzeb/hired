"""CV generation: the model picks bullet ids from the profile, plain code checks
the pick and fills the page, then preview and PDF export."""

import json
import re
from datetime import date

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlmodel import select

from .db import SessionDep
from . import taxonomy
from .model import choose, generate_json, notice, served
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
from .tables import Application, current_profile

router = APIRouter(tags=["generate"])


class GenerateRequest(BaseModel):
    # Name a model to answer with, or leave empty for the configured routing.
    model: str = ""
    # The row this selection belongs to, if it has been saved. Given it, the
    # chosen bullets are recorded now rather than only at export: an email is
    # written from them, and requiring a PDF first made a posting you apply to
    # in a text box impossible to write for.
    application_id: int | None = None
    jd_text: str
    parsed_jd: ParsedJd = ParsedJd()
    title_variant: str | None = None


class GenerateResponse(BaseModel):
    cv: GeneratedCv
    flags: list[Flag]
    # Which model answered, so a fallback is visible rather than silent.
    model: str = ""
    # Said out loud when the first answer was unusable and the call was repeated.
    notice: str = ""


TITLE_ASK = """Pick the framing this CV should use for the posting below.

Each option says when it applies. The posting decides which one, nothing else:
not the order they are listed in, and not which projects the CV will show.

{options}

Answer with one id, copied exactly."""

BULLETS_ASK = """Choose the {most} bullets from this one project that best evidence
what the posting asks for, strongest first.

You are not writing anything. You return ids, and the page is built from these
exact sentences afterwards, so anything you invent is discarded.

Prefer a bullet that evidences something the posting explicitly asks for over one
that is merely impressive. If fewer than {most} are relevant, return only those.

PROJECT: {name}
{bullets}

WHAT THE POSTING ASKS FOR:
{asks}

Answer with bullet ids, copied exactly."""

TITLE_SCHEMA = {
    "type": "object",
    "properties": {"title_id": {"type": "string"}},
    "required": ["title_id"],
}
BULLETS_SCHEMA = {
    "type": "object",
    "properties": {"bullet_ids": {"type": "array", "items": {"type": "string"}}},
    "required": ["bullet_ids"],
}


def _select(profile: Profile, jd_text: str, body: "GenerateRequest") -> dict:
    """
    Four small questions instead of one big one.

    Asked as a single call, this picked one project out of sixteen and a mobile
    framing for a web posting, on four runs out of four. Asked separately, the
    same model got the title right nine times out of nine and returned identical
    bullets three times out of three. It is good at a small judgement and bad at
    ranking sixteen things while filling a coverage table in the same breath,
    which is the same lesson the fit check already learned when its two halves
    were split.

    Which projects is not asked at all. The model offered a project with no
    overlap with the posting; code ranks them by what they cover, which is
    deterministic and cannot invent.
    """
    rules = profile.rules
    jd = body.parsed_jd

    title_id = body.title_variant or str(
        generate_json(
            TITLE_ASK.format(
                options="\n".join(f"- {t.id}: use when {t.use_when}" for t in profile.titles)
            )
            + f"\n\nPOSTING:\n{jd_text}",
            TITLE_SCHEMA,
            local="first",
            good=lambda answer: bool(str(answer.get("title_id") or "").strip()),
        ).get("title_id")
        or ""
    )

    asks = jd.model_dump_json()
    sections = []
    for project in _rank(profile, jd, rules.max_projects, title_id):
        pool = [b for b in project.bullets if b.status != "blocked"]
        answer = generate_json(
            BULLETS_ASK.format(
                most=rules.max_bullets_per_project,
                name=project.name,
                bullets="\n".join(f"- {b.id}: {b.text}" for b in pool),
                asks=asks,
            ),
            BULLETS_SCHEMA,
            local="first",
            # No `good` here. Nothing is a real answer: asked which of a crypto
            # analysis platform's bullets suit a front-end posting, the honest
            # reply is none, and _select already drops the project. Guarding it
            # turned that into a 502 and the whole CV failed.
        )
        ids = [str(i) for i in answer.get("bullet_ids") or []]
        if ids:
            sections.append({"project_id": project.id, "bullet_ids": ids})

    return {"title_id": title_id, "sections": sections}


def _wants(jd: ParsedJd) -> list[tuple[str, int, set[str], str]]:
    """
    Everything the posting asks for: name, weight, its words, and its kind.

    Once per thing. One reading listed monitoring twice, and "React" beside
    "React.js" is one requirement counted twice, which moves the score.
    """
    seen: set[frozenset[str]] = set()
    out: list[tuple[str, int, set[str], str]] = []
    for skill, weight in [
        *((s, s.importance) for s in jd.required_skills),
        *((s, 1) for s in jd.preferred_skills),
    ]:
        words = _terms(skill.name)
        key = frozenset(words)
        if key in seen:
            continue
        seen.add(key)
        out.append((skill.name, weight, words, skill.kind))
    return out


def _evidence(project: Project) -> set[str]:
    """The words a project can answer to, with what its stack honestly implies."""
    live = [bullet.text for bullet in project.bullets if bullet.status != "blocked"]
    return taxonomy.implied(
        _terms(" ".join(live + project.stack + project.tags)), project.stack + project.tags
    )


def _belongs(project: Project, jd: ParsedJd | None, title: str) -> bool:
    """Mobile work only on a mobile title or a posting that asks for mobile."""
    if "mobile" not in project.tags or title == "mobile":
        return True
    return any(
        {"mobile", "ios", "android"} & words or {"react", "native"} <= words
        for _name, _weight, words, _kind in (_wants(jd) if jd else [])
    )


def _rank(profile: Profile, jd: ParsedJd, limit: int, title: str = "") -> list[Project]:
    """
    The projects that between them back the most of what the posting asks for.

    Taking the `limit` most relevant projects separately is not the same thing:
    for a posting wanting React and SQL it returned five front-end projects and
    left the database work off, because every one of them scored well on the
    same words. Each pick here is worth what it adds to the ones already chosen,
    so the second database project is worth less than the first.

    Divided by the project's own priority. Counting words alone, a single-user
    personal tool and a live product with a team of ten scored the same, and a
    crypto analysis platform topped a front-end posting on the strength of its
    stack list. The priority is the one the person wrote, so it is theirs to
    tune, and it is the only knob: status and scale are already in it.

    The chosen title is a tag too. Ranked by words alone, a React Native chat
    app led a web front-end posting on the strength of the word "React", three
    mobile bullets deep. Counting it half still left it second. So mobile work
    stays off the page entirely unless the title is mobile or the posting asks
    for it: a reader who sees React Native files the CV under mobile.
    # ponytail: one direction only. Mirror it for mobile postings if a web
    # project ever tops one; it has not happened yet.

    Three model-based rankers were measured first and all failed at temperature
    0: a 66-bullet list came back in file order, a 16-project menu came back in
    file order, and a 0-10 relevance score came back 7 or 8 for everything. A
    local model picks well within one project and cannot rank across them.
    """
    wants = _wants(jd)
    pool = [
        project
        for project in profile.all_projects()
        if any(bullet.status != "blocked" for bullet in project.bullets)
        and _belongs(project, jd, title)
    ]
    # The reader's label and the code backstop both, as the fit and the
    # coverage already do. Trusting the label alone let "desire to own code
    # quality" count six points for a mobile app on a web posting.
    scorable = [
        (name, weight, words)
        for name, weight, words, kind in wants
        if kind != "trait" and _non_bullet(name, profile) != "not something a CV evidences"
    ]
    covers = {
        project.id: {
            name: weight
            for name, weight, words in scorable
            if taxonomy.backs(words, _evidence(project))
        }
        for project in pool
    }

    chosen: list[Project] = []
    covered: set[str] = set()

    def fresh(project: Project) -> int:
        return sum(w for name, w in covers[project.id].items() if name not in covered)

    def gain(project: Project) -> tuple[float, int]:
        # Overlap counts a little. Counting only what was new, an agency's
        # WordPress hosting work outranked the React product on a React
        # posting because it alone mentioned the cloud. Priority breaks ties,
        # so a posting that names nothing a bullet mentions still gets a page.
        total = sum(covers[project.id].values())
        return (fresh(project) + total / 4) / max(project.priority, 1), -project.priority

    # Four projects fill a page and five is the most it holds. Past four, only
    # new coverage earns a place. Six came back once, trimmed to a bullet each.
    cap = min(limit, 5)
    while pool and len(chosen) < cap:
        best = max(pool, key=gain)
        if len(chosen) >= min(cap, 4) and not fresh(best):
            break
        covered |= covers[best.id].keys()
        chosen.append(best)
        pool.remove(best)

    # One of your own projects in a free slot, when one answers the posting at
    # all: four employer projects left room for one and printed none. It never
    # displaces employer work the posting asked for.
    own = [project for project in pool if project in profile.projects and covers[project.id]]
    if own and not any(project in profile.projects for project in chosen) and len(chosen) < cap:
        chosen.append(max(own, key=gain))
    return chosen


@router.post("/generate")
def generate(body: GenerateRequest, session: SessionDep) -> GenerateResponse:
    choose(body.model)
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

    answer = _select(profile, text, body)
    cv, flags = _assemble(profile, answer, body.title_variant, body.parsed_jd)

    if body.application_id is not None:
        row = session.get(Application, body.application_id)
        if row is not None:
            _remember(row, cv)
            session.add(row)
            session.commit()

    return GenerateResponse(cv=cv, flags=flags, model=served.get(), notice=notice.get())


def _remember(row: Application, cv: GeneratedCv) -> None:
    """The selection, on the row. Export overwrites it with what actually printed."""
    row.title_variant = cv.title
    row.summary_text = cv.summary
    row.selected_bullet_ids = [b.id for s in cv.sections for b in s.bullets]
    row.selected_bullets = [
        {"id": bullet.id, "text": bullet.text, "project_name": section.project_name}
        for section in cv.sections
        for bullet in section.bullets
    ]
    row.coverage = [item.model_dump() for item in cv.coverage]


def _pool(profile: Profile) -> list[Bullet]:
    """Bullets the model may pick from. Blocked ones are left out entirely."""
    return [
        bullet
        for project in profile.all_projects()
        for bullet in project.bullets
        if bullet.status != "blocked"
    ]


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
                    type="warn",
                    message=f'The selector named a project that does not exist, '
                    f'"{entry.get("project_id")}". Nothing was printed for it.',
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

    _fill_page(profile, title, summary, sections, projects, rules, flags, jd)

    printed = " ".join(
        [summary.text if summary else ""]
        + [
            part
            for section in sections
            for part in [section.project_name, section.label, " ".join(section.stack)]
        ]
        + [bullet.text for section in sections for bullet in section.bullets]
    )
    # What the page says before any one project speaks: the summary, and the
    # headings it prints under. A standalone project sits beneath PROJECTS,
    # which is what "personal project" means next to WORK EXPERIENCE.
    standalone = {project.id for project in profile.projects}
    context = _terms(summary.text if summary else "") | {"experience", "work"}
    if standalone & {section.project_id for section in sections}:
        context |= {"project", "personal"}
    _check_qualifiers(sections, projects, context, flags)
    _check_banned(rules, printed, flags)

    lines = _skills(profile, {section.project_id for section in sections}, jd)
    cv = GeneratedCv(
        title=_headline(title.text, lines, jd) if title else "",
        summary=summary.text if summary else "",
        skills_lines=lines,
        sections=sections,
        coverage=_coverage(jd, answer, sections, profile),
    )
    if not sections:
        # A real block: there is no page to export, rather than a page with
        # something wrong on it.
        flags.append(Flag(type="block", message="Nothing was selected, so there is no CV."))
    return cv, flags


def _bullets(project: Project, ids: list, rules, flags: list[Flag]) -> list[SelectedBullet]:
    by_id = {bullet.id: bullet for bullet in project.bullets}
    chosen: list[SelectedBullet] = []
    # Once each: the model has returned the same id twice and it printed twice.
    for raw in list(dict.fromkeys(ids))[: rules.max_bullets_per_project]:
        bullet = by_id.get(str(raw))
        if bullet is None:
            flags.append(
                Flag(
                    type="warn",
                    message=f'The selector named a bullet that is not in "{project.name}", '
                    f'"{raw}". It was dropped, so nothing invented reached the page.',
                )
            )
            continue
        if bullet.status == "blocked":
            # Never in the pool, so this id came from somewhere else. Refuse it.
            flags.append(
                Flag(
                    type="warn",
                    message=f'Blocked bullet "{bullet.id}" was selected anyway and refused. '
                    f"{bullet.blocked_reason or 'No reason was recorded.'}",
                )
            )
            continue
        chosen.append(
            SelectedBullet(id=bullet.id, text=bullet.text, source_id=bullet.id, rephrased=False)
        )
    # In the order written, not the order picked: a project's second bullet
    # opens "Built it on Next.js", and printed alone or first it reads as
    # nonsense. Trimming takes from the tail, so the lead line survives.
    order = {bullet.id: i for i, bullet in enumerate(project.bullets)}
    return sorted(chosen, key=lambda bullet: order[bullet.id])


# A requirement no bullet can answer. Matched here rather than asked of the model,
# because the answer is a lookup in the profile and a lookup cannot be wrong.
_SCHOOLING = re.compile(r"\b(degree|diploma|bachelor|master|b\.?sc|m\.?sc|post-secondary|graduate)\b", re.I)
_DISPOSITION = re.compile(
    r"\b(communication|communicate|problem.solving|critical thinking|curiosity|curious"
    r"|patience|patient|attention to detail|detail.oriented|self.starter|self.motivated"
    r"|motivated|willingness|eagerness|interest in|passion|team player|interpersonal"
    r"|collaborat|work(ing)? independently|independently and|multiple projects|multitask"
    r"|desire to learn|eager to learn|keen to learn|fast learner|quick learner"
    r"|self.learning|learning ability|time management|organisational|organizational"
    r"|adaptab|flexib|work ethic|proactive|positive attitude|strong work"
    r"|desire to|ux principles?|design principles?)\b",
    re.I,
)
# ponytail: a named list, not a blanket "ability to" or "strong desire", which
# would swallow "ability to design REST APIs". Add names as postings show them.

# Facts about the person, not skills. A posting naming one is not describing
# something a CV can evidence, so it counts neither for nor against.
_NOT_A_SKILL = re.compile(
    r"\b(non.disclosure|non.compete|agreement|clearance|security check|background check"
    r"|work authorisation|work authorization|eligib|citizen|permanent resident|visa"
    r"|driver.s licen|references|willing to travel|relocat|overtime|on.call)\b",
    re.I,
)


_YEARS = re.compile(r"\b(\d+)\s*\+?\s*(?:(?:to|-|\u2013)\s*\d+\s*)?\+?\s*years?\b", re.I)


def _months(start: str, end: str) -> set[tuple[int, int]]:
    """Every calendar month from start to end, both "YYYY-MM"; no end or "present" is now."""
    try:
        y, m = map(int, start[:7].split("-"))
        ey, em = map(int, end[:7].split("-")) if end[:4].isdigit() else (date.today().year, date.today().month)
    except ValueError:
        return set()
    out = set()
    while (y, m) <= (ey, em):
        out.add((y, m))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def _years(skill: str, profile: Profile) -> str:
    """
    "3 to 5 years of experience" answered from the employment dates.

    No bullet can say how long you have worked, so every posting stating years
    reported it as a gap. Months are counted once, so overlapping jobs do not
    add up. A named skill with its own recorded years is judged on those.
    """
    found = _YEARS.search(skill)
    if not found:
        return ""
    lowered = skill.casefold()
    own = next(
        (e for e in profile.skill_evidence if e.years and re.search(rf"\b{re.escape(e.name.casefold())}\b", lowered)),
        None,
    )
    if own:
        have, what = own.years, f"{own.years:g} years of {own.name}"
    else:
        months: set[tuple[int, int]] = set()
        for job in profile.experience:
            months |= _months(job.start, job.end)
        have = int(len(months) / 12 * 10) / 10
        what = f"{have:g} years of experience"
    return what if have >= int(found.group(1)) else ""


def _non_bullet(skill: str, profile: Profile) -> str:
    """What backs this requirement if no bullet ever could."""
    if years := _years(skill, profile):
        return years
    if _SCHOOLING.search(skill) and profile.education:
        top = profile.education[0]
        return f"{top.degree} {top.field}".strip() or top.school
    if _DISPOSITION.search(skill) or _NOT_A_SKILL.search(skill):
        return "not something a CV evidences"
    return ""


def _coverage(
    jd: ParsedJd, answer: dict, sections: list[CvSection], profile: Profile
) -> list[SkillCoverage]:
    """
    What the printed page backs, read off the page itself.

    Asked for this as a third job in the selection call, the model returned
    entries for requirements that were not in the posting and left real ones
    empty. The bullets are known and the requirements are known, so nothing here
    needs a model: a bullet backs a requirement when it uses its words.

    The page prints more than bullets: a stack line per project and the skills
    block. JavaScript was reported unbacked with "JavaScript" sitting in the
    skills block and TypeScript on three stack lines, because only the bullets
    were read.
    """
    printed = [item for section in sections for item in section.stack[:4]] + [
        item for row in _skills(profile, {s.project_id for s in sections}, jd) for item in row.items
    ]

    def on_page(words: set[str]) -> str:
        return next(
            (item for item in printed if taxonomy.backs(words, taxonomy.implied(_terms(item), [item]))),
            "",
        )

    return [
        SkillCoverage(
            skill=name,
            bullet_ids=[
                bullet.source_id or bullet.id
                for section in sections
                for bullet in section.bullets
                if taxonomy.backs(words, taxonomy.implied(_terms(bullet.text), [bullet.text]))
            ],
            backed_by=_non_bullet(name, profile) or on_page(words),
        )
        for name, _weight, words, _kind in _wants(jd)
    ]


_FIGURE = re.compile(r"\d+(?:\.\d+)?\s*%?")


def _about_one_bullet(qualifier: str, project: Project) -> str:
    """
    The bullet a qualifier is about, when it is about one in particular.

    "The 50% figure is estimated, not measured" qualifies the bullet carrying
    50%, and says nothing about a page that does not print it. "Prototype only,
    never shipped" qualifies the project itself and returns nothing here.
    """
    figures = set(_FIGURE.findall(qualifier))
    if not figures:
        return ""
    for bullet in project.bullets:
        carried = set(_FIGURE.findall(bullet.text))
        if figures & carried:
            return bullet.id
    return ""


def _check_qualifiers(sections, projects, context: set[str], flags: list[Flag]) -> None:
    """
    Warn when a project's required qualifier is missing from the printed page.

    Checked against that project's own words plus what the page says as a whole,
    never against another project's. Matched against the whole page by
    substring, "Solo build" on one project was answered by "native rebuilds" in
    another project's bullet, and the caveat went unsaid.
    """
    for section in sections:
        project = projects[section.project_id]
        on_page = {bullet.source_id or bullet.id for bullet in section.bullets}
        says = context | _terms(
            " ".join(
                [section.project_name, section.label, " ".join(section.stack)]
                + [bullet.text for bullet in section.bullets]
            )
        )
        for qualifier in project.claim_boundary.required_qualifiers:
            # A caveat about a figure is not owed when the figure is not printed.
            tied = _about_one_bullet(qualifier, project)
            if tied and tied not in on_page:
                continue
            # Keyword overlap, since the qualifier rarely appears word for word.
            # "Solo build" is answered by a bullet saying "solo"; four letters count.
            words = {w for w in _terms(qualifier) if len(w) > 3}
            if words and not words & says:
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


# Below MIN_FILL the page gets topped up; a bullet that pushes it past one page
# is undone. At 0.90 a page with room for a whole project stopped at 0.93.
MIN_FILL = 0.96


# Words that carry no signal in a requirement: "Experience with React" and
# "React" ask for the same thing.
_FILLER = frozenset(
    "a an and or the of in on for to with using strong clear basic solid good"
    " experience knowledge working familiarity understanding exposure ability"
    " skills skill years proficiency demonstrated related least one"
    # "open source contribution with code review" was answered by "opened a
    # second checkout page" and by "code" in any bullet at all.
    " code open source"
    # "Figma handoff" is Figma; a posting says "based on Figma models".
    " handoff".split()
)


# "React.js" and "React" are the same thing; so are "Node.js", "NodeJS" and
# "Node". Only a trailing js, so a bare "JS" survives as a word of its own.
_DOT_JS = re.compile(r"(?<=[A-Za-z])[.\s]?js\b", re.I)


def _terms(text: str) -> set[str]:
    """
    The meaningful words in a requirement or a bullet. Hyphens and slashes split,
    because a posting writes "pull-request workflows" and a bullet writes
    "reviewing pull requests", and those are the same thing.

    Dots split too, so ".NET" and "ASP.NET Core" meet on "net". The js suffix
    goes first: stripping plurals turned "React.js" into "react.j", which met
    nothing, so a posting spelling it that way reported React as a gap for a
    React developer.
    """
    plain = re.sub(r"[-\u2010-\u2015/]", " ", text)
    plain = _DOT_JS.sub("", plain)
    plain = plain.replace(".", " ")
    return {_singular(w) for w in _words(plain) if len(w) > 1} - _FILLER


def _singular(word: str) -> str:
    """One trailing s, off words long enough to have a plural.

    rstrip("s") took every trailing s, so CSS became "c" and collided with the
    C language, and JS became "j".
    """
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def _relevance(text: str, jd: ParsedJd) -> int:
    """
    How much of what the posting asks for this text names, weighted by importance.

    Word overlap, not substring: a parsed requirement reads "TypeScript or
    JavaScript with React", which appears verbatim in no bullet ever written.

    # ponytail: whole words, so "SQL" does not match "PostgreSQL". Stemming or
    # an alias table if that costs real matches; a model if it needs meaning.
    """
    have = _terms(text)
    return sum(
        skill.importance
        for skill in [*jd.required_skills, *jd.preferred_skills]
        if _terms(skill.name) & have
    )


def _fill_page(profile, title, summary, sections, projects, rules, flags, jd) -> None:
    """Add unused bullets in priority order until the page is full, measured in Chromium."""
    def build() -> GeneratedCv:
        lines = _skills(profile, {s.project_id for s in sections}, jd)
        return GeneratedCv(
            title=_headline(title.text, lines, jd) if title else "",
            summary=summary.text if summary else "",
            skills_lines=lines,
            sections=sections,
        )

    on_page = {b.source_id for s in sections for b in s.bullets}
    used = {s.project_id for s in sections}
    own = {project.id for project in profile.projects}
    # Projects already on the page first, then one of your own projects if none
    # is printed, then the rest. Within that, the most relevant bullet to this
    # posting, then the person's own priority. Filling by priority alone put
    # unrelated work on the page to make up the height. The mobile rule holds
    # here too, or a React Native app walks on through the back door.
    spare: list[tuple[Project, Bullet]] = sorted(
        (
            (project, bullet)
            for project in profile.all_projects()
            if _belongs(project, jd, title.id if title else "")
            for bullet in project.bullets
            if bullet.id not in on_page and bullet.status != "blocked"
        ),
        key=lambda pair: (
            pair[0].id not in used,
            not (pair[0].id in own and not own & used),
            -_relevance(f"{pair[1].text} {' '.join(pair[0].stack)}", jd),
            pair[1].priority,
        ),
    )

    try:
        with measurer() as pages:
            filled = started = pages(render_html(profile, build()))
            added = dropped = 0

            # The selector used to come back short, so this loop only ever added.
            # Code now picks a full slate, which overruns the page as easily as it
            # falls short: the first live run printed two pages. Trim from the
            # tail, which is the least relevant project's weakest bullet.
            while filled > 1.0 and sum(len(s.bullets) for s in sections) > 1:
                # Your own project is there for its one line, so it gives up
                # the rest first. Then third bullets, lowest ranked project
                # first: taking the tail section whole cut the only .NET work
                # off a posting that asked for .NET. Then from the tail, your
                # own project last, so a page is never five one-bullet projects.
                most = max(len(s.bullets) for s in sections)
                extra = next((s for s in sections if s.project_id in own and len(s.bullets) > 1), None)
                last = extra or (
                    next(s for s in reversed(sections) if len(s.bullets) == most)
                    if most > 2
                    else next((s for s in reversed(sections) if s.project_id not in own), sections[-1])
                )
                last.bullets.pop()
                if not last.bullets:
                    sections.remove(last)
                filled = pages(render_html(profile, build()))
                dropped += 1
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
                # A shorter one further down may still fit, so keep looking.
                if grown > 1.0:
                    section.bullets.pop()
                    if fresh:
                        sections.remove(section)
                    continue
                filled, added = grown, added + 1

            if dropped:
                flags.append(
                    Flag(
                        type="warn",
                        message=f"Dropped {dropped} bullet{'s' if dropped > 1 else ''} to keep "
                        f"this to one page: it came to {started:.2f} of a page, now "
                        f"{filled:.2f}. The weakest evidence went first.",
                    )
                )
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


def _asked(item: str, wants: list[set[str]]) -> int:
    """2 when the posting names the item, 1 when it names what the item implies, else 0.

    The item whole, never word by word: "React Hook Form" answered a posting
    asking for React and led the row.
    """
    own = _terms(item)
    if any(taxonomy.backs(words, {" ".join(sorted(own))}) for words in wants):
        return 2
    return int(any(taxonomy.backs(words, taxonomy.implied(own, [item]) - own) for words in wants))


def _headline(text: str, lines: list[SkillsLine], jd: ParsedJd | None) -> str:
    """
    The written title's role, then the posting's own words for what it backs.

    "Front-End Engineer | React · Next.js · TypeScript · Design Systems" went
    to a posting asking for JavaScript, HTML and CSS. The role stays as
    written, never the posting's: "Software Developer II" is vague and
    "Senior" is a claim. Fewer than two matches keeps the written list.
    """
    role, _, written = text.partition("|")
    if not jd or not written:
        return text
    # By the posting's own weight: React Native, required, came after
    # TypeScript, an asset, because the Frontend row is written first.
    wants = [(words, w) for _name, w, words, kind in _wants(jd) if kind != "trait"]

    # Then the more specific name: "React" also answers "React Native".
    def weight(item: str) -> tuple[int, int, int]:
        return max(
            ((w, _asked(item, [words]), len(_terms(item))) for words, w in wants if _asked(item, [words])),
            default=(0, 0, 0),
        )

    items = [item for line in lines for item in line.items]
    asked = sorted((i for i in items if weight(i)[0]), key=lambda i: weight(i), reverse=True)
    return f"{role.strip()} | {' · '.join(asked[:4])}" if len(asked) >= 2 else text


# ponytail: characters, not measured width. "Label: a · b · c" at 10pt Inter
# fills the content box at about this many; measure in Chromium if rows wrap.
_SKILLS_ROW_CHARS = 100


def _skills(profile: Profile, selected: set[str], jd: ParsedJd | None = None) -> list[SkillsLine]:
    """
    The skills block, one printed line per row, tailored to the posting.

    Printed whole, it ran to five rows of up to seventeen items, wrapping to
    seven or eight lines, and put Sanity and WordPress on a C++ posting. Within
    a row, what the posting names comes first, then what a printed project
    uses, then the rest, until the line is full. A row with neither is dropped,
    keeping at least three. Row order stays as written.

    Gated skills print only when a project evidencing them is on the page.
    """
    printed = [project for project in profile.all_projects() if project.id in selected]
    tags = {tag.lower() for project in printed for tag in project.tags}
    used = {item.lower() for project in printed for item in project.stack}
    evidenced = {
        skill.name.lower()
        for skill in profile.skill_evidence
        if any(project in selected for project in skill.evidence)
    }
    wants = [words for _name, _w, words, kind in _wants(jd) if kind != "trait"] if jd else []

    def score(item: str) -> int:
        asked = _asked(item, wants)
        return asked + 1 if asked else 1 if item.lower() in used | evidenced else 0

    rows: list[tuple[int, SkillsLine]] = []
    for row in profile.skills:
        # A whole row that belongs to one kind of work: no Mobile row on a web page.
        if row.only_with and not {tag.lower() for tag in row.only_with} & tags:
            continue
        gated = {item.lower() for item in row.gated}
        allowed = [
            item for item in row.items if item.lower() not in gated or item.lower() in evidenced
        ]
        ranked = sorted(allowed, key=score, reverse=True) if jd else allowed
        items: list[str] = []
        for item in ranked:
            if len(f"{row.line}: " + " · ".join(items + [item])) > _SKILLS_ROW_CHARS:
                break
            items.append(item)
        # never_standalone earns its place only next to something else.
        alone = {item.lower() for item in row.never_standalone}
        if len(items) == 1 and items[0].lower() in alone:
            items = []
        if items:
            rows.append((max(map(score, items)) if jd else 1, SkillsLine(line=row.line, items=items)))

    keep = {id(line) for best, line in rows if best}
    for _best, line in rows:
        if len(keep) >= 3:
            break
        keep.add(id(line))
    return [line for _best, line in rows if id(line) in keep]


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
    # The model that chose these bullets, carried from the generate response.
    model: str = ""


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
    row.filename = filename(profile.identity.name, row.company)
    # Snapshot of what was sent, as printed: it can differ from what was
    # selected, since bullets can be deselected between the two.
    _remember(row, body.cv)
    row.model = body.model or row.model
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
        skills_lines=_skills(
            profile,
            {section.project_id for section in sections},
            ParsedJd.model_validate(row.jd_parsed) if row.jd_parsed else None,
        ),
        sections=sections,
    )
    pdf, pages = to_pdf(render_html(profile, cv))

    # Only the bytes and the name. A re-render must not rewrite what was sent.
    row.pdf = pdf
    row.filename = filename(profile.identity.name, row.company)
    session.add(row)
    session.commit()
    session.refresh(row)
    return ExportResponse(id=row.id, filename=row.filename, page_count=pages, dropped=missing)
