"""Pydantic models mirroring the master profile. These are the API contract."""

from typing import Annotated, Any
from urllib.parse import urlparse

from pydantic import BaseModel, BeforeValidator, model_validator

# ponytail: YAML turns 2024-11-01 into a date object; coerce back to string.
Str = Annotated[str, BeforeValidator(str)]


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


class Identity(BaseModel):
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


class Summary(BaseModel):
    id: str
    text: str
    max_chars: int = 520


class SkillLine(BaseModel):
    line: str
    items: list[str]
    never_standalone: list[str] = []
    gated: list[str] = []


class ClaimBoundary(BaseModel):
    can_claim: list[str] = []
    cannot_claim: list[str] = []
    required_qualifiers: list[str] = []


class Bullet(BaseModel):
    id: str
    text: str
    priority: int = 3
    tags: list[str] = []
    status: str = "active"  # active | blocked


class Project(BaseModel):
    id: str
    name: str
    label: str = ""
    stack: list[str] = []
    priority: int = 3
    tags: list[str] = []
    disclosure: str = ""
    # Repo, live demo, case study, app store listing.
    links: Links = []
    claim_boundary: ClaimBoundary = ClaimBoundary()
    bullets: list[Bullet] = []


class Experience(BaseModel):
    name: str
    role: str = ""
    start: Str = ""
    end: Str = ""
    location: str = ""
    priority: int = 3
    projects: list[Project] = []


class Education(BaseModel):
    school: str
    degree: str = ""
    field: str = ""
    location: str = ""
    start: Str = ""
    end: Str = ""
    notes: str = ""
    links: Links = []


class Certification(BaseModel):
    name: str
    issuer: str = ""
    date: Str = ""
    url: str = ""


class Language(BaseModel):
    name: str
    level: str = ""


class Profile(BaseModel):
    identity: Identity
    titles: list[Title] = []
    summaries: list[Summary] = []
    skills: list[SkillLine] = []
    experience: list[Experience] = []
    education: list[Education] = []
    certifications: list[Certification] = []
    languages: list[Language] = []

    @model_validator(mode="after")
    def unique_ids(self):
        # A duplicate id means the selector can point at the wrong claim, and a
        # duplicate project id means a section of the CV renders twice. Both are
        # cheaper to catch here than to debug in a generated PDF.
        bullets: set[str] = set()
        projects: set[str] = set()
        for exp in self.experience:
            for proj in exp.projects:
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
    projects: int
    bullets: int
    blocked: int
    missing_boundaries: int


class ValidationResult(BaseModel):
    ok: bool
    errors: list[ProfileIssue] = []
    warnings: list[ProfileIssue] = []
    summary: ProfileSummary | None = None


# ---------- the parsed posting ----------


class RequiredSkill(BaseModel):
    name: str
    importance: int = 2


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
