"""
The fit check: paste a posting, find out whether it is worth your evening.

This runs before anything is saved and before any CV exists, because the point
is not to read the posting. It answers two questions in one model call: what the
posting actually asks for, and how that lands against the profile.

It writes nothing. Saving is a separate decision and a separate route, which is
what makes "discard" free: you close the tab and no row exists.
"""

import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlmodel import select

from .db import SessionDep
from .model import generate_json
from .models import Fit, ParsedJd, Profile
from .profile_parser import parse_text
from .tables import ProfileSource

router = APIRouter(tags=["fit"])


class FitRequest(BaseModel):
    jd_text: str


class FitResponse(BaseModel):
    parsed_jd: ParsedJd
    fit: Fit


# What Google is told to return. Kept beside the prompt, because changing one
# without the other is how a schema and its instructions drift apart.
SCHEMA = {
    "type": "object",
    "properties": {
        "parsed_jd": {
            "type": "object",
            "properties": {
                "company": {"type": "string"},
                "role": {"type": "string"},
                "seniority": {"type": "string"},
                "location": {"type": "string"},
                "work_mode": {"type": "string"},
                "required_skills": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "importance": {
                                "type": "integer",
                                "minimum": 1,
                                "maximum": 3,
                            },
                        },
                        "required": ["name", "importance"],
                    },
                },
                "preferred_skills": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "importance": {
                                "type": "integer",
                                "minimum": 1,
                                "maximum": 3,
                            },
                        },
                        "required": ["name", "importance"],
                    },
                },
                "keywords": {"type": "array", "items": {"type": "string"}},
                "french_required": {"type": "boolean"},
                "years_required": {"type": "integer"},
            },
            "required": ["company", "role", "required_skills", "keywords"],
        },
        "score": {"type": "integer", "minimum": 1, "maximum": 10},
        "reasoning": {"type": "string"},
        "gaps": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["parsed_jd", "score", "reasoning", "gaps"],
}

INSTRUCTIONS = """You are scoring one job posting against one candidate's profile.

The profile is the only thing you know about this person. It is deliberately
honest: it records what they cannot claim as carefully as what they can.

Extract what the posting asks for, then score the fit from 1 to 10.

  1-3   out of their league, or a different discipline entirely
  4-6   real overlap but a gap they cannot close before applying
  7-8   a good fit with something worth knowing about
  9-10  they are what the posting describes

Rules:

- Never credit them with anything the profile does not evidence. A skill absent
  from skills and skill_evidence is a skill they do not have.
- The gaps section is the person's own list of what they cannot do. Treat it as
  fact. If the posting needs something listed there, that is a gap, whatever
  else the profile suggests.
- cannot_claim is binding. Never let a project count as evidence for something
  its cannot_claim excludes.
- A gated skill counts only when a project evidencing it exists.
- Compare years honestly. skill_evidence carries years and last_used; a posting
  asking for more than the profile shows is a gap even if the skill is listed.
- Every gap must be one specific thing the posting requires and the profile does
  not evidence. Not advice, not a list of what they should learn.
- The reasoning is two or three sentences, addressed to the person, naming the
  evidence you scored on. No flattery.
- Skill importance is 1 to 3: 3 is a hard requirement the posting leads with,
  2 is a real expectation, 1 is a passing mention.
- Say plainly when the answer is that they should not apply. Being told to skip
  a posting is the most useful thing this can do."""


@router.post("/fit")
def check_fit(body: FitRequest, session: SessionDep) -> FitResponse:
    text = (body.jd_text or "").strip()
    if len(text) < 80:
        raise HTTPException(
            422, "That is too short to score. Paste the requirements, not just the title."
        )

    row = session.exec(select(ProfileSource)).first()
    if row is None:
        raise HTTPException(404, "No profile saved yet. There is nothing to score against.")

    prompt = (
        f"{INSTRUCTIONS}\n\nPROFILE:\n{json.dumps(context(parse_text(row.text)))}"
        f"\n\nPOSTING:\n{text}"
    )
    answer = generate_json(prompt, SCHEMA)

    return FitResponse(
        parsed_jd=ParsedJd.model_validate(answer.get("parsed_jd") or {}),
        fit=Fit(
            # Clamped rather than trusted. The schema asks for 1 to 10 and Gemini
            # has handed back 55 for the same request shape, and a score outside
            # the range renders as a broken meter rather than an error.
            score=max(1, min(10, int(answer.get("score", 0)))),
            reasoning=str(answer.get("reasoning", "")),
            gaps=[str(gap) for gap in answer.get("gaps") or []],
        ),
    )


def context(profile: Profile) -> dict:
    """
    The part of the profile that scoring needs, which is not all of it.

    Bullet text is left out on purpose: nothing here decides what to print, and
    sending the whole file would triple the prompt to no benefit. What goes in is
    what the posting gets compared against, plus every constraint that could turn
    an apparent match into a gap.
    """
    return {
        "titles": [{"id": t.id, "use_when": t.use_when} for t in profile.titles],
        "skills": [
            {
                "line": row.line,
                "items": row.items,
                "gated": row.gated,
                "never_standalone": row.never_standalone,
            }
            for row in profile.skills
        ],
        "skill_evidence": [
            {
                "name": s.name,
                "years": s.years,
                "last_used": s.last_used,
                "level": s.level,
                "context": s.context,
                "gated": s.gated,
                "evidence": s.evidence,
            }
            for s in profile.skill_evidence
        ],
        "projects": [
            {
                "id": p.id,
                "name": p.name,
                "label": p.label,
                "stack": p.stack,
                "tags": p.tags,
                "my_role": p.my_role,
                "domain": p.domain,
                "status": p.status,
                "cannot_claim": p.claim_boundary.cannot_claim,
            }
            for p in profile.all_projects()
        ],
        "employers": [
            {"name": e.name, "role": e.role, "start": e.start, "end": e.end}
            for e in profile.experience
        ],
        "education": [
            {"school": e.school, "degree": e.degree, "field": e.field} for e in profile.education
        ],
        "certifications": [
            {"name": c.name, "status": c.status} for c in profile.certifications
        ],
        "languages": [{"name": lang.name, "level": lang.level} for lang in profile.languages],
        "gaps": [g.model_dump() for g in profile.gaps],
        "availability": profile.availability.model_dump(),
    }
