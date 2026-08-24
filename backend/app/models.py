"""Pydantic models mirroring the master profile. These are the API contract."""

from typing import Annotated, Any
from urllib.parse import urlparse

from pydantic import BaseModel, BeforeValidator, field_validator, model_validator

# ponytail: YAML turns 2024-11-01 into a date object; coerce back to string.
Str = Annotated[str, BeforeValidator(str)]

# Documented in the template as "one of". Lowercased on the way in so a file
# written with "Native" or "Full-Time" both stops warning and starts matching:
# these are tokens the code branches on, not prose anybody reads.
Token = Annotated[str, BeforeValidator(lambda v: str(v).strip().lower() if v else "")]


class Loose(BaseModel):
    """
    A base that reads a written-but-empty list as an empty list.

        cannot_claim:
        bullets:

    YAML calls both of those None, and Pydantic calls None a type error, which
    refuses the whole save. Mid-draft is not a reason to lose the file, and this
    is the one place every model can inherit it from rather than each list field
    carrying its own validator.
    """

    @model_validator(mode="before")
    @classmethod
    def _empty_lists(cls, data):
        if not isinstance(data, dict):
            return data
        listy = {
            name
            for name, field in cls.model_fields.items()
            if "list[" in str(field.annotation).replace("List[", "list[")
        }
        return {
            key: ([] if value is None and key in listy else value)
            for key, value in data.items()
        }


def _as_link(value: Any) -> Any:
    """
    People write links three ways and all three are unambiguous, so all three
    parse:

        - label: Repo
          url: github.com/me/thing
        - Repo: github.com/me/thing
        - github.com/me/thing
    """
    if isinstance(value, str):
        host = urlparse(value if "//" in value else f"//{value}").netloc
        return {"label": host.removeprefix("www.") or value, "url": value}
    if isinstance(value, dict) and "url" not in value and len(value) == 1:
        label, url = next(iter(value.items()))
        return {"label": str(label), "url": str(url)}
    return value


class Link(BaseModel):
    label: str
    url: str


Links = Annotated[list[Link], BeforeValidator(lambda v: [_as_link(x) for x in v or []])]


class Meta(BaseModel):
    """Bookkeeping. schema_version is what lets an old file be migrated later."""

    schema_version: int = 1
    updated: Str = ""


class Identity(Loose):
    # Only the name is required. A profile missing a phone number is incomplete,
    # not unparseable, and refusing to load it helps nobody.
    name: str
    location: str = ""
    email: str = ""
    phone: Str = ""
    linkedin: str = ""
    github: str = ""
    portfolio: str = ""
    # Anything else in the header: Dribbble, Stack Overflow, a paper, a talk.
    # A fixed field per site would need a code change per site.
    links: Links = []
    relocation: str = ""
    authorization: str = ""


class Title(BaseModel):
    id: str
    text: str
    # Not printed. It tells the selector which framing a posting calls for.
    use_when: str = ""


class Summary(BaseModel):
    id: str
    text: str
    max_chars: int = 520


class SkillLine(Loose):
    line: str
    items: list[str]
    never_standalone: list[str] = []
    gated: list[str] = []


class SkillEvidence(Loose):
    """
    Never printed. It is how "5+ years of React" gets answered from the file
    rather than guessed, and how a gated skill gets refused when the project
    that evidences it is not on the page.
    """

    name: str
    years: float | None = None
    last_used: Str = ""
    level: Token = ""  # familiar | working | advanced | expert
    context: Token = ""  # professional | personal | academic
    # Project ids, from Experience or Projects, that prove it.
    evidence: list[str] = []
    gated: bool = False


class ClaimBoundary(Loose):
    can_claim: list[str] = []
    cannot_claim: list[str] = []
    required_qualifiers: list[str] = []


class Metric(BaseModel):
    """Where a number in a bullet came from. Absent is itself an answer."""

    value: str = ""
    source: Token = "none"  # measured | estimated | reported | none
    method: str = ""


class Bullet(Loose):
    id: str
    text: str
    priority: int = 3
    tags: list[str] = []
    status: Token = "active"  # active | blocked
    # An alternative wording for when the page is one line too long. Same claim.
    short: str = ""
    metric: Metric | None = None
    # Why it is blocked. Without it nobody can act on it later, including you.
    blocked_reason: str = ""


class Project(Loose):
    id: str
    name: str
    label: str = ""
    stack: list[str] = []
    # Your actual scope, in the words you would use under questioning.
    my_role: str = ""
    status: Token = ""  # live | shipped | internal | pilot | sunset | abandoned
    domain: str = ""
    start: Str = ""
    end: Str = ""
    # Not printed. The answer when an interviewer asks why this exists.
    why_built: str = ""
    priority: int = 3
    tags: list[str] = []
    disclosure: str = ""
    # True things you cannot evidence today. Each should have a blocked bullet.
    unverified: list[str] = []
    # Repo, live demo, case study, app store listing.
    links: Links = []
    claim_boundary: ClaimBoundary = ClaimBoundary()
    bullets: list[Bullet] = []


class PreviousRole(BaseModel):
    """A promotion inside the same employer. Newest first, current one excluded."""

    role: str = ""
    start: Str = ""
    end: Str = ""


class Experience(Loose):
    name: str
    role: str = ""
    start: Str = ""
    end: Str = ""
    location: str = ""
    # Printed only when it is not full-time: omitting a contract or a volunteer
    # arrangement reads as a lie the moment somebody checks.
    employment_type: Token = ""
    context: str = ""
    # What you may say about this employer in public. Not printed.
    disclosure: str = ""
    previous_roles: list[PreviousRole] = []
    priority: int = 3
    projects: list[Project] = []


class Education(Loose):
    school: str
    degree: str = ""
    field: str = ""
    location: str = ""
    start: Str = ""
    end: Str = ""
    # Off the page by default, here so they can be switched on for a posting
    # that asks. Usually a new-grad one.
    gpa: Str = ""
    coursework: list[str] = []
    notes: str = ""
    priority: int = 3
    links: Links = []


class Certification(BaseModel):
    name: str
    issuer: str = ""
    date: Str = ""
    # "earned" on purpose: a file written before this field existed has no
    # status, and everything in it was real.
    status: Token = "earned"  # earned | in_progress | expired
    expires: Str = ""
    url: str = ""


class Publication(BaseModel):
    type: Token = ""  # talk | article | paper | patent | book | podcast
    title: str
    venue: str = ""
    date: Str = ""
    url: str = ""


class Award(BaseModel):
    name: str
    issuer: str = ""
    date: Str = ""
    note: str = ""


class Language(BaseModel):
    name: str
    level: Token = ""  # native | fluent | professional | conversational | basic
    # Where the level needs a caveat. Printed after the level when present.
    note: str = ""


class Gap(BaseModel):
    """
    Never printed. The register of what you cannot do, so the selector reports
    a gap instead of stretching a bullet to cover it.
    """

    skill: str
    status: Token = ""  # none | learning | personal-only | rusty
    bridge: str = ""
    blocks: str = ""


class Availability(Loose):
    """Never printed. What lets a posting be scored before an hour goes into it."""

    work_modes: list[str] = []
    locations: list[str] = []
    earliest_start: Str = ""
    notice_period: str = ""
    employment_types: list[str] = []
    # Free-shaped on purpose: currency, minimum, target, note, whatever else.
    compensation: dict = {}
    travel_ok: str = ""
    deal_breakers: list[str] = []
    will_not_work_on: list[str] = []


class Rules(Loose):
    """Never printed. Generation constraints that apply to every CV from this file."""

    banned_words: list[str] = []
    banned_chars: list[str] = []
    preferred_phrasing: dict[str, str] = {}
    max_bullets_per_project: int = 3
    max_projects: int = 5
    page_limit: int = 1


class Profile(Loose):
    meta: Meta = Meta()
    identity: Identity
    titles: list[Title] = []
    summaries: list[Summary] = []
    skills: list[SkillLine] = []
    skill_evidence: list[SkillEvidence] = []
    experience: list[Experience] = []
    # Work with no employer: personal builds, open source, academic.
    projects: list[Project] = []
    education: list[Education] = []
    certifications: list[Certification] = []
    publications: list[Publication] = []
    awards: list[Award] = []
    languages: list[Language] = []
    availability: Availability = Availability()
    gaps: list[Gap] = []
    rules: Rules = Rules()

    def all_projects(self) -> list[Project]:
        """Every project, wherever it lives. Employment is not what makes one."""
        return [p for exp in self.experience for p in exp.projects] + self.projects

    @model_validator(mode="after")
    def unique_ids(self):
        # A duplicate id means the selector can point at the wrong claim, and a
        # duplicate project id means a section of the CV renders twice. Both are
        # cheaper to catch here than to debug in a generated PDF.
        #
        # The project namespace spans Experience and Projects together: a bullet
        # id resolves to one project, so the same id in both lists is ambiguous
        # rather than merely repetitive.
        bullets: set[str] = set()
        projects: set[str] = set()
        for proj in self.all_projects():
            if proj.id in projects:
                raise ValueError(f"duplicate project id: {proj.id}")
            projects.add(proj.id)
            for b in proj.bullets:
                if b.id in bullets:
                    raise ValueError(f"duplicate bullet id: {b.id}")
                bullets.add(b.id)
        return self


# ---------- validation (POST /api/profile/validate) ----------


class ProfileIssue(BaseModel):
    """1-indexed line in the file the person typed, or None when not line-bound."""

    line: int | None = None
    message: str


class ProfileSummary(BaseModel):
    # projects is what sits under an employer, which is what it has always
    # meant. projects_total counts the standalone Projects section as well.
    projects: int
    projects_total: int = 0
    bullets: int
    blocked: int
    missing_boundaries: int
    skills_evidenced: int = 0
    gaps: int = 0
    unverified: int = 0


class ValidationResult(BaseModel):
    ok: bool
    errors: list[ProfileIssue] = []
    warnings: list[ProfileIssue] = []
    summary: ProfileSummary | None = None


# ---------- the parsed posting ----------


class RequiredSkill(BaseModel):
    name: str
    importance: int = 2

    @field_validator("importance")
    @classmethod
    def _one_to_three(cls, value: int) -> int:
        # Clamped, not refused. Gemini answers 5 on this three-point scale often
        # enough, and a tooltip reading "importance 5" is not worth a failed
        # request. Every producer goes through here, so it is fixed once.
        return max(1, min(3, value))


class Fit(BaseModel):
    """
    How a posting lands against the profile. Never stored on its own: it either
    becomes an Application row or the tab gets closed.
    """

    score: int = 0
    reasoning: str = ""
    # Each one a specific thing the posting requires and the profile does not
    # evidence. The half of this app worth keeping when you do not apply.
    gaps: list[str] = []


class SelectedBullet(BaseModel):
    """
    A bullet as it will print. `text` is copied from the profile, never composed:
    the selector returns ids and this is assembled from them afterwards.
    """

    id: str
    text: str
    # Which profile bullet it came from. Equal to id today, and kept separate
    # because the short variant will eventually make them differ.
    source_id: str
    rephrased: bool = False


class SkillsLine(BaseModel):
    line: str
    items: list[str]


class CvSection(BaseModel):
    project_id: str
    project_name: str
    label: str = ""
    stack: list[str] = []
    bullets: list[SelectedBullet] = []


class GeneratedCv(BaseModel):
    title: str = ""
    summary: str = ""
    skills_lines: list[SkillsLine] = []
    sections: list[CvSection] = []


class Flag(BaseModel):
    """block stops the export. warn is a decision a person has to make."""

    type: str  # block | warn
    message: str


class ParsedJd(BaseModel):
    """
    What the JD parser pulls out, and what an application row stores.

    Every field has a default so a sparse dict widens into a shape the UI can
    render. Typed rather than left as a bare dict because the frontend contract
    promises these arrays exist, and a missing one blanks the whole page.
    """

    company: str = ""
    role: str = ""
    seniority: str = ""
    location: str = ""
    work_mode: str = ""
    required_skills: list[RequiredSkill] = []
    preferred_skills: list[RequiredSkill] = []
    keywords: list[str] = []
    french_required: bool = False
    years_required: int | None = None
