"""Pydantic models for the profile file, parsed postings and generated CVs."""

from typing import Annotated, Any
from urllib.parse import urlparse

from pydantic import BaseModel, BeforeValidator, field_validator, model_validator

# YAML parses 2024-11-01 as a date; coerce it back to a string.
Str = Annotated[str, BeforeValidator(str)]

# Enum-like strings, lowercased so matching is case-insensitive.
Token = Annotated[str, BeforeValidator(lambda v: str(v).strip().lower() if v else "")]


class Loose(BaseModel):
    """Treat an empty YAML list (None) as []."""

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
    """Accept a {label, url}, a one-key {label: url}, or a bare URL string."""
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
    schema_version: int = 1
    updated: Str = ""


class Identity(Loose):
    name: str
    location: str = ""
    email: str = ""
    phone: Str = ""
    linkedin: str = ""
    github: str = ""
    portfolio: str = ""
    links: Links = []
    relocation: str = ""
    authorization: str = ""


class Title(BaseModel):
    id: str
    text: str
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
    """Not printed. Used for years-of-experience answers and to gate skills."""

    name: str
    years: float | None = None
    last_used: Str = ""
    level: Token = ""  # familiar | working | advanced | expert
    context: Token = ""  # professional | personal | academic
    evidence: list[str] = []
    gated: bool = False


class ClaimBoundary(Loose):
    can_claim: list[str] = []
    cannot_claim: list[str] = []
    required_qualifiers: list[str] = []


class Metric(BaseModel):
    """Where a number in a bullet came from."""

    value: str = ""
    source: Token = "none"  # measured | estimated | reported | none
    method: str = ""


class Bullet(Loose):
    id: str
    text: str
    priority: int = 3
    tags: list[str] = []
    status: Token = "active"  # active | blocked
    short: str = ""
    metric: Metric | None = None
    blocked_reason: str = ""


class Project(Loose):
    id: str
    name: str
    label: str = ""
    stack: list[str] = []
    my_role: str = ""
    status: Token = ""  # live | shipped | internal | pilot | sunset | abandoned
    domain: str = ""
    start: Str = ""
    end: Str = ""
    why_built: str = ""
    priority: int = 3
    tags: list[str] = []
    disclosure: str = ""
    # False prints the bullets under the employer with no bold project lead-in.
    named: bool = True
    unverified: list[str] = []
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
    employment_type: Token = ""
    context: str = ""
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
    gpa: Str = ""
    coursework: list[str] = []
    notes: str = ""
    priority: int = 3
    links: Links = []


class Certification(BaseModel):
    name: str
    issuer: str = ""
    date: Str = ""
    # Defaults to earned so older files without this field stay correct.
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
    note: str = ""


class Gap(BaseModel):
    """Not printed. A skill the person lacks."""

    skill: str
    status: Token = ""  # none | learning | personal-only | rusty
    bridge: str = ""
    blocks: str = ""


class Availability(Loose):
    """Not printed. Used to score a posting's fit."""

    work_modes: list[str] = []
    locations: list[str] = []
    earliest_start: Str = ""
    notice_period: str = ""
    employment_types: list[str] = []
    compensation: dict = {}
    travel_ok: str = ""
    deal_breakers: list[str] = []
    will_not_work_on: list[str] = []


class Rules(Loose):
    """Not printed. Limits applied to every generated CV."""

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
        return [p for exp in self.experience for p in exp.projects] + self.projects

    @model_validator(mode="after")
    def unique_ids(self):
        # Ids are unique across experience and projects so a bullet id maps to one project.
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


class ProfileIssue(BaseModel):
    line: int | None = None  # 1-indexed, None when not tied to a line
    message: str


class ProfileSummary(BaseModel):
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


class RequiredSkill(BaseModel):
    name: str
    importance: int = 2

    @field_validator("importance")
    @classmethod
    def _one_to_three(cls, value: int) -> int:
        # Clamp rather than reject: models sometimes answer out of range.
        return max(1, min(3, value))


class Fit(BaseModel):
    score: int = 0
    reasoning: str = ""
    gaps: list[str] = []


class SelectedBullet(BaseModel):
    """A bullet as printed. `text` is copied from the profile, never written by the model."""

    id: str
    text: str
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
    named: bool = True
    bullets: list[SelectedBullet] = []


class SkillCoverage(BaseModel):
    """A skill the posting asks for and the printed bullets that back it. Empty means a gap."""

    skill: str
    bullet_ids: list[str] = []


class GeneratedCv(BaseModel):
    title: str = ""
    summary: str = ""
    skills_lines: list[SkillsLine] = []
    sections: list[CvSection] = []
    coverage: list[SkillCoverage] = []


class Flag(BaseModel):
    """block stops the export; warn needs a person to decide."""

    type: str  # block | warn
    message: str


class ParsedJd(BaseModel):
    """Parsed job posting. Everything defaults so a sparse parse still works."""

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
