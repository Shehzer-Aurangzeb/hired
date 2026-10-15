"""Fit check: one model call parses a job posting and scores it against the profile."""

import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from sqlmodel import select

from .db import SessionDep
from .generate import _non_bullet, _terms
from .model import generate_json, served
from .models import Fit, ParsedJd, Profile
from .profile_parser import parse_text
from .tables import Application, ProfileSource, current_profile, stamp

router = APIRouter(tags=["fit"])


class FitRequest(BaseModel):
    jd_text: str


class PriorApplication(BaseModel):
    id: int
    role: str
    status: str
    created_at: str
    applied_at: str | None = None


class FitResponse(BaseModel):
    parsed_jd: ParsedJd
    fit: Fit
    # Which model answered, so a fallback is visible rather than silent.
    model: str = ""
    # Earlier applications to the same company.
    seen: list[PriorApplication] = []


_SKILLS = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "importance": {"type": "integer", "minimum": 1, "maximum": 3},
        },
        "required": ["name", "importance"],
    },
}

# What the posting asks for. Read out of the posting alone, with no profile in
# the context to compete for attention.
EXTRACT_SCHEMA = {
    "type": "object",
    "properties": {
        "company": {"type": "string"},
        "role": {"type": "string"},
        "seniority": {"type": "string"},
        "location": {"type": "string"},
        "work_mode": {"type": "string"},
        "required_skills": _SKILLS,
        "preferred_skills": _SKILLS,
        "years_required": {"type": "integer"},
    },
    "required": ["company", "role", "required_skills", "preferred_skills"],
}

# The verdict, given that list and the profile.
SCORE_SCHEMA = {
    "type": "object",
    "properties": {
        "score": {"type": "integer", "minimum": 1, "maximum": 10},
        "reasoning": {"type": "string"},
        "gaps": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["score", "reasoning", "gaps"],
}

EXTRACT = """Extract what this job posting asks for. You are reading one document
and filling in a form about it. You are not judging anyone against it.

- One entry per thing the posting names. Never merge several into a category:
  "testing, CI/CD, DevOps, source control" is four entries, not one.
- A name, not a sentence. "React", "CI/CD", "a two-year diploma" are names.
  Quoting a whole bullet back is not extracting it, and a requirement written
  as a paragraph matches nothing later.
- required_skills is everything under requirements, qualifications or the day
  to day work. preferred_skills is everything under nice to have, assets,
  bonus or "it would be great if". Both lists matter; preferred is rarely empty.
- importance is 1 to 3: 3 the posting leads with it or calls it required, 2 a
  real expectation, 1 a passing mention.
- Miss nothing. A requirement you leave out is one the reader never sees."""

# ponytail: entries come back at the granularity of the posting's own bullets,
# so one can still read "testing, code reviews, CI/CD and source control".
# _relevance tokenises, so matching survives it; only the coverage chips read
# long. Split them in code if that ever matters more than it does now.

INSTRUCTIONS = """You are scoring one job posting against one candidate's profile.

The profile is the only thing you know about this person. It is deliberately
honest: it records what they cannot claim as carefully as what they can.

What the posting asks for has already been read out of it for you. Score the
fit from 1 to 10.

  1-3   out of their league, or a different discipline entirely
  4-6   real overlap but a gap they cannot close before applying
  7-8   a good fit with something worth knowing about
  9-10  they are what the posting describes

Rules:

- Never credit them with anything the profile does not evidence. A skill absent
  from skills and skill_evidence is a skill they do not have.
- The gaps section is the person's own list of what they cannot do. Treat it as
  fact. If the posting needs something listed there, that is a gap, whatever
  else the profile suggests. If the posting does not ask for it, it is not a gap
  for this posting, however honestly it is listed.
- cannot_claim is binding. Never let a project count as evidence for something
  its cannot_claim excludes.
- A gated skill counts only when a project evidencing it exists.
- A skill_evidence entry with an empty evidence list is a tool they have used
  but cannot tie to a listed project. Credit it as familiarity: enough that they
  are not starting from nothing, never as depth, and never as the thing that
  makes them a fit. Do not report it as a gap.
- A skill listed under skills with no skill_evidence entry is claimed but not
  detailed. They have used it. Credit it as present, never as depth, and do not
  report it as a gap. The gap is depth, if the posting asks for depth.
- A gap is something the profile does not have. Eligibility, clearances and work
  authorisation are facts about the person, not skills; name one as a gap only
  when the profile itself says they lack it. Dispositions are not gaps either:
  no profile evidences communication, curiosity or attention to detail.
- Compare years honestly. skill_evidence carries years and last_used; a posting
  asking for more than the profile shows is a gap even if the skill is listed.
- Every gap must be one specific thing the posting requires and the profile does
  not evidence. Not advice, not a list of what they should learn.
- The reasoning is two or three sentences, addressed to the person, naming the
  evidence you scored on. No flattery.
- Say plainly when the answer is that they should not apply. Being told to skip
  a posting is the most useful thing this can do."""


@router.post("/fit")
def check_fit(body: FitRequest, session: SessionDep) -> FitResponse:
    text = (body.jd_text or "").strip()
    if len(text) < 80:
        raise HTTPException(
            422, "That is too short to score. Paste the requirements, not just the title."
        )

    row = current_profile(session)
    if row is None:
        raise HTTPException(404, "No profile saved yet. There is nothing to score against.")

    # Two calls, each with one job. Done together, the extraction half lost a
    # third of the requirements with the profile sitting in the same context.
    parsed_jd = ParsedJd.model_validate(
        generate_json(f"{EXTRACT}\n\nPOSTING:\n{text}", EXTRACT_SCHEMA, local="first")
    )
    read_by = served.get()

    profile = parse_text(row.text)
    try:
        answer = generate_json(
            f"{INSTRUCTIONS}\n\nPROFILE:\n{json.dumps(context(profile))}"
            f"\n\nWHAT THE POSTING ASKS FOR:\n{parsed_jd.model_dump_json()}"
            f"\n\nPOSTING:\n{text}",
            SCORE_SCHEMA,
        )
        scored_by = served.get()
    except HTTPException:
        # Busy is not an answer on the day you are applying, and the local model
        # answers this one by inventing experience. Count instead.
        score, reasoning, gaps = _without_a_model(profile, parsed_jd)
        answer = {"score": score, "reasoning": reasoning, "gaps": gaps}
        scored_by = "counted, no model"

    return FitResponse(
        parsed_jd=parsed_jd,
        model=f"{read_by} + {scored_by}" if read_by != scored_by else read_by,
        seen=_seen(session, parsed_jd.company),
        fit=Fit(
            # Clamp: the model sometimes returns scores outside 1-10.
            score=max(1, min(10, int(answer.get("score", 0)))),
            reasoning=str(answer.get("reasoning", "")),
            gaps=[str(gap) for gap in answer.get("gaps") or []],
        ),
    )


def _without_a_model(profile: Profile, jd: ParsedJd) -> tuple[int, str, list[str]]:
    """
    A score with no model in it, for when Gemini will not answer.

    Every input is a lookup in the profile, so it cannot invent experience. The
    local model can and did: asked to score, it reported Azure, open source
    contributions and authoring GraphQL APIs, none of which are in the file.
    Dull and checkable beats fluent and false.
    """
    have = {w for row in profile.skills for item in row.items for w in _terms(item)}
    have |= {w for entry in profile.skill_evidence for w in _terms(entry.name)}
    # Per gap, not one flat pile: flattened, a gap for "React Native" lent its
    # "react" to the pile and reported React as a gap for a React developer.
    # A gap blocks a requirement only when every word of it is in that
    # requirement, so "React Native" blocks React Native and nothing else.
    cannot = [(_terms(gap.skill), gap.skill) for gap in profile.gaps]

    met: list[str] = []
    missing: list[str] = []
    points = possible = 0
    # Preferred skills count for less, not nothing: a posting writes that list
    # precisely to tell applicants apart.
    for skill, weight in [
        *((s, s.importance) for s in jd.required_skills),
        *((s, 1) for s in jd.preferred_skills),
    ]:
        backing = _non_bullet(skill.name, profile)
        if backing == "not something a CV evidences":
            continue  # neither met nor missing: no profile answers it
        possible += weight
        words = _terms(skill.name)
        if backing:  # a degree, answered by the education section
            points += weight
            met.append(skill.name)
        elif named := next((g for terms, g in cannot if terms and terms <= words), ""):
            missing.append(f"{skill.name} (your own gaps list says {named})")
        elif words & have:
            # ponytail: whole words only. "SQL" therefore misses "PostgreSQL",
            # which costs a point; matching inside words made "cloud" match
            # "Cloudflare" and scored Azure as met, which costs an application.
            points += weight
            met.append(skill.name)
        else:
            missing.append(skill.name)

    # Clamped to the middle, because counting words cannot earn either extreme.
    # A posting asking for "AI capability" and "software engineering best
    # practices" names nothing a skills list contains, and scored 1 of 10 for a
    # job worth applying to. Never "definitely skip", never "definitely apply".
    score = round(3 + 5 * points / possible) if possible else 5
    return (
        max(3, min(8, score)),
        f"Counted, not judged: Gemini would not answer, so this is {len(met)} of "
        f"{len(met) + len(missing)} things the posting names appearing in your "
        "profile. It cannot read a requirement written as a description rather "
        "than a technology, so it stays off both ends of the scale. Run it again "
        "when Gemini is free.",
        missing,
    )


def _seen(session: SessionDep, company: str) -> list[PriorApplication]:
    # Exact case-insensitive match, so "Shopify Inc." and "Shopify" differ.
    name = (company or "").strip()
    if not name:
        return []
    rows = session.exec(
        select(Application)
        .where(func.lower(Application.company) == name.lower())
        .order_by(Application.created_at.desc())
        .limit(5)
    ).all()
    return [
        PriorApplication(
            id=row.id,
            role=row.role,
            status=row.status,
            created_at=stamp(row.created_at) or "",
            applied_at=stamp(row.applied_at),
        )
        for row in rows
    ]


def context(profile: Profile) -> dict:
    """The slice of the profile that scoring needs (no bullet text)."""
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
