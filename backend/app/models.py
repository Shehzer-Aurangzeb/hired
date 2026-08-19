"""Pydantic models mirroring profile/master.md. These are the API contract."""

from typing import Annotated

from pydantic import BaseModel, BeforeValidator, model_validator

# ponytail: YAML turns 2024-11-01 into a date object; coerce back to string.
Str = Annotated[str, BeforeValidator(str)]


class Identity(BaseModel):
    name: str
    location: str
    email: str
    phone: Str
    linkedin: str
    github: str
    portfolio: str = ""
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
    claim_boundary: ClaimBoundary = ClaimBoundary()
    bullets: list[Bullet] = []


class Experience(BaseModel):
    name: str
    role: str
    start: Str
    end: Str
    location: str = ""
    priority: int = 3
    projects: list[Project] = []


class Profile(BaseModel):
    identity: Identity
    titles: list[Title] = []
    summaries: list[Summary] = []
    skills: list[SkillLine] = []
    experience: list[Experience] = []

    @model_validator(mode="after")
    def unique_bullet_ids(self):
        # A duplicate id means the selector can point at the wrong claim. Catch it at parse.
        seen = set()
        for exp in self.experience:
            for proj in exp.projects:
                for b in proj.bullets:
                    if b.id in seen:
                        raise ValueError(f"duplicate bullet id: {b.id}")
                    seen.add(b.id)
        return self
