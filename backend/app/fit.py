"""Fit check: one model call parses a job posting and scores it against the profile."""

import json
import re

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from sqlmodel import select

from . import taxonomy
from .db import SessionDep
from .generate import _non_bullet, _terms, _wants
from .model import available, choose, generate_json, notice, served
from .models import Fit, ParsedJd, Profile
from .profile_parser import parse_text
from .settings import get_settings
from .tables import Application, current_profile, stamp

router = APIRouter(tags=["fit"])


@router.get("/models")
def models() -> dict:
    """What the screen may choose between, and what it gets if it chooses nothing."""
    settings = get_settings()
    return {"models": available(settings), "configured": settings.ollama_model}


class FitRequest(BaseModel):
    jd_text: str
    # Name a model to answer with, or leave empty for the configured routing.
    model: str = ""


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
    # Said out loud when the first answer was unusable and the call was repeated.
    notice: str = ""
    # Earlier applications to the same company.
    seen: list[PriorApplication] = []


_SKILLS = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "importance": {"type": "integer", "minimum": 1, "maximum": 3},
            "kind": {"type": "string", "enum": ["skill", "trait"]},
        },
        "required": ["name", "importance", "kind"],
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

# Prose only. The score and the gaps are worked out in code and handed over,
# because a model asked to decide them reported the person was missing React.
SCORE_SCHEMA = {
    "type": "object",
    "properties": {"reasoning": {"type": "string"}},
    "required": ["reasoning"],
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
- kind is "skill" or "trait". A skill is something a CV can show: a technology,
  a tool, a named practice like code review or CI/CD. A trait is a disposition
  or soft competency: communication, curiosity, working independently, coaching
  others, keeping up with industry trends, judgement under pressure. If a CV
  could not prove it, it is a trait. When torn, choose skill.
- Miss nothing. A requirement you leave out is one the reader never sees."""

# ponytail: entries come back at the granularity of the posting's own bullets,
# so one can still read "testing, code reviews, CI/CD and source control".
# _relevance tokenises, so matching survives it; only the coverage chips read
# long. Split them in code if that ever matters more than it does now.

INSTRUCTIONS = """Write the two or three sentences a person reads before deciding
whether to apply for this job.

The work is already done. You are given what the posting asks for, which of
those the profile covers, which it does not, and a score. All of it was worked
out from the profile itself, so all of it is true.

Your only job is to say it in plain prose, addressed to the person.

- Never add a gap. The list you are given is the complete list. If something is
  not on it, they have it, however it looks to you.
- Never remove a gap or soften one into a strength.
- Never change the score or quote a different one.
- Name the strongest thing they have for this posting and the gap that matters
  most. Those two facts are the whole message.
- Two or three sentences. Not a cover letter, not a study plan, nothing written
  in their voice, no advice about what to go and learn, no flattery."""


def _alternatives(name: str) -> list[str]:
    """
    A requirement split on the choices it offers.

    "TypeScript or JavaScript with React, or C# with .NET" is met by React
    alone. Read whole it matches nothing, and the model called it a gap for a
    React developer.
    """
    parts = re.split(r",?\s+\bor\b\s+|\s*/\s*", name)
    return [part for part in (p.strip(" .,:;") for p in parts) if part]


def requirements(profile: Profile, jd: ParsedJd) -> tuple[list[str], list[str], int]:
    """
    Which of the posting's requirements the profile covers, which it does not,
    and the score that follows. No model involved: every answer is a lookup.

    A model asked the same question said the person lacked React, lacked a
    degree they hold, and lacked French the posting never mentioned.
    """
    backs = _backs(profile)
    # Per gap, not one flat pile: flattened, a gap for "React Native" lent its
    # "react" to the pile and reported React as a gap for a React developer.
    cannot = [(_terms(gap.skill), gap.skill) for gap in profile.gaps]

    met: list[str] = []
    unmet: list[str] = []
    points = possible = 0
    for name, weight, _words, kind in _wants(jd):
        schooling = _non_bullet(name, profile)
        if kind == "trait" or schooling == "not something a CV evidences":
            continue  # a disposition: no profile evidences it either way
        possible += weight

        if schooling:  # a degree, answered by the education section
            met.append(f"{name} — {schooling}")
            points += weight
            continue

        # Any one of the choices on offer is enough.
        choices = _alternatives(name)
        blocked = next(
            (
                said
                for terms, said in cannot
                if terms
                and (terms <= _terms(name) or any(terms <= _terms(c) for c in choices))
            ),
            "",
        )
        backing = sorted(
            {backs[word] for choice in choices for word in _terms(choice) & backs.keys()}
        )
        if not blocked and backing:
            # Named, because the requirement's own words are not proof of
            # anything: handed "exposure to Azure or another cloud platform"
            # as met, the model wrote that the candidate has used Azure.
            named = ", ".join(b for b in backing[:3] if _terms(b) != _terms(name))
            met.append(f"{name} — {named}" if named else name)
            points += weight
            continue

        unmet.append(
            f"{name} (your own gaps list says {blocked})" if blocked
            else _near_miss(name, set(backs))
        )

    # Clamped off both ends: this counts requirements, and a posting asking for
    # "AI capability" names nothing a skills list holds however good the fit.
    score = round(2 + 7 * points / possible) if possible else 5
    return met, _once(unmet), max(2, min(9, score))


def _once(names: list[str]) -> list[str]:
    """In order, without repeats: one posting was read as wanting monitoring twice."""
    return list(dict.fromkeys(names))


def _backs(profile: Profile) -> dict[str, str]:
    """
    Every word the profile can answer to, mapped to the skill that answers it.

    The mapping is the point. Knowing a requirement is met is not enough to say
    it in a sentence without inventing something.
    """
    # The line names too: a "Backend" row of nine tools answers "back-end
    # development", which otherwise read as a gap for a full-stack developer.
    named = [row.line for row in profile.skills]
    named += [item for row in profile.skills for item in row.items]
    named += [entry.name for entry in profile.skill_evidence]
    named += [word for project in profile.all_projects() for word in project.stack]

    backs: dict[str, str] = {}
    for name in named:
        for word in taxonomy.implied(_terms(name), [name]):
            backs.setdefault(word, name)
    return backs


def _near_miss(name: str, have: set[str]) -> str:
    """Say what they have in the same category, which is not the same as having it."""
    found = taxonomy.category_of(name)
    if found:
        _category, members = found
        close = sorted(m for m in members if _terms(m) <= have and _terms(m) != _terms(name))
        if close:
            return f"{name} (you have {close[0]}, which is close but not the same)"
    return name


def _three_sentences(text: str) -> str:
    """
    The prompt asks for three; measured output ran to eleven.

    The lookbehind keeps "M.S. in Applied Computer Science" as one sentence,
    which it is: without it the degree ate one of the three.
    """
    parts = re.split(r"(?<![A-Z]\.)(?<=[.!?])\s+(?=[A-Z])", " ".join(text.split()))
    return " ".join(parts[:3]).strip()


@router.post("/fit")
def check_fit(body: FitRequest, session: SessionDep) -> FitResponse:
    choose(body.model)
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
        generate_json(
            f"{EXTRACT}\n\nPOSTING:\n{text}",
            EXTRACT_SCHEMA,
            local="first",
            # A posting with no requirements in it is not a posting. This came
            # back empty once and every later step ran against the empty list.
            good=lambda answer: bool(answer.get("required_skills")),
        )
    )
    read_by = served.get()
    said = notice.get()

    profile = parse_text(row.text)
    met, unmet, score = requirements(profile, parsed_jd)

    # Busy is not an answer on the day you are applying. The local model takes
    # about a minute and reads plainer, and its name travels with the score.
    answer = generate_json(
        f"{INSTRUCTIONS}\n\nWHAT THE POSTING ASKS FOR:\n{parsed_jd.model_dump_json()}"
        f"\n\nWHAT THEY HAVE, FROM THEIR PROFILE:\n"
        + ("\n".join(f"- {name}" for name in met) or "- nothing the posting names")
        + "\n\nWHAT THEY DO NOT HAVE. THIS LIST IS COMPLETE:\n"
        + ("\n".join(f"- {name}" for name in unmet) or "- nothing; they cover all of it")
        + f"\n\nSCORE: {score} out of 10",
        SCORE_SCHEMA,
        local="fallback",
        good=lambda answer: bool(str(answer.get("reasoning") or "").strip()),
    )
    scored_by = served.get()
    said = said or notice.get()

    return FitResponse(
        parsed_jd=parsed_jd,
        model=f"{read_by} + {scored_by}" if read_by != scored_by else read_by,
        notice=said,
        seen=_seen(session, parsed_jd.company),
        fit=Fit(
            # Both worked out in code. The model only wrote the sentences.
            score=score,
            reasoning=_three_sentences(str(answer.get("reasoning", ""))),
            gaps=unmet,
        ),
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
