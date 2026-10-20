"""
The email and the form answer, written from an application already scored.

The model is never asked what to say. Code works that out from the row — the
company, the strongest bullets for this posting, what the profile covers, the
gap — and the model only joins it into prose. That split is the one that fixed
the fit reasoning, where output went from eleven fabricated sentences to three
accurate ones the moment the facts arrived already decided.

See docs/artifacts.md for why, and for what this deliberately does not promise.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .db import SessionDep
from .fit import requirements
from .generate import _check_banned, _relevance
from .model import choose, generate_json, served
from .models import Flag, ParsedJd
from .profile_parser import parse_text
from .tables import Application, current_profile, now, stamp

router = APIRouter(prefix="/applications", tags=["artifacts"])

KINDS = ("email", "answer")

# Enough to carry the point and not a word more. A recruiter skims; a form has a
# character limit. Both punish padding, which is also what the model reaches for
# when it has nothing to say.
MOST_BULLETS = 3

SCHEMA = {
    "type": "object",
    "properties": {"subject": {"type": "string"}, "body": {"type": "string"}},
    "required": ["subject", "body"],
}

EMAIL = """Write a short email applying for this job. The CV is attached, so the
email does not repeat it: it gives a reason to open it.

Four sentences at most. A subject line of under nine words naming the role.

- Open with the role and where it was seen, in one clause. No "I hope this finds
  you well", no "I am writing to apply for".
- Then the two specifics below, in the candidate's own words, numbers included.
  Those numbers are measured; do not round them, soften them or drop them.
- Close with one plain line. No "I would welcome the opportunity to discuss how
  my skills can contribute to your team's continued success".

Never write: excited, thrilled, passionate, delighted, deeply, truly, dive in,
leverage, synergy, robust, cutting-edge, innovative, game-changing, dynamic,
seamless, spearheaded, "proven track record", "hit the ground running",
"perfect fit", "as you can see from my CV", "I am confident that".

You are given everything there is to say. Add no fact, no company research, no
flattery about the company, and no claim about what the candidate enjoys or
believes. If the gap below is named, one honest half-sentence about it is
better than silence; do not apologise for it."""

ANSWER = """Answer this application form question as the candidate.

Answer the question that was asked, in its own terms, and stop. No greeting, no
sign-off, no restating the question back.

- Lead with the answer, not with a wind-up.
- Support it with the specifics below, in the candidate's own words, numbers
  included. Those numbers are measured; do not round or soften them.
- Three or four sentences unless the question plainly wants more.

Never write: excited, thrilled, passionate, delighted, deeply, truly, dive in,
leverage, synergy, robust, cutting-edge, innovative, game-changing, dynamic,
seamless, spearheaded, "proven track record", "hit the ground running",
"perfect fit", "I am confident that".

You are given everything there is to say. Add no fact, no company research and
no flattery. Say the subject is empty."""


class ArtifactIn(BaseModel):
    kind: str
    # Required for an answer, ignored for an email.
    question: str = ""
    # Which model to write it. Empty means the configured routing.
    model: str = ""


class ArtifactOut(BaseModel):
    kind: str
    question: str = ""
    subject: str = ""
    body: str
    model: str = ""
    created_at: str = ""
    # Banned phrases that reached the text. The caller decides what to do.
    flags: list[Flag] = []


def facts(row: Application, profile) -> dict:
    """
    What there is to say, worked out rather than asked for.

    Only the bullets that printed: they are the evidence chosen for this posting,
    already filtered through the claim guard, and already in his own sentences.
    """
    jd = ParsedJd.model_validate(row.jd_parsed or {})
    bullets = sorted(
        (b for b in row.selected_bullets if (b.get("text") or "").strip()),
        key=lambda b: -_relevance(b["text"], jd),
    )[:MOST_BULLETS]

    met, unmet, _score = requirements(profile, jd) if profile else ([], [], 5)
    return {
        "candidate": profile.identity.name if profile else "",
        "company": row.company,
        "role": row.role,
        "evidence": [b["text"] for b in bullets],
        "covers": met[:6],
        "gap": (row.gaps or unmet)[:1],
    }


def _prompt(kind: str, question: str, known: dict) -> str:
    head = EMAIL if kind == "email" else ANSWER
    lines = [
        head,
        f"\nCANDIDATE: {known['candidate']}",
        f"COMPANY: {known['company']}",
        f"ROLE: {known['role']}",
        "\nTHE TWO OR THREE SPECIFICS, IN THEIR OWN WORDS:",
        *(f"- {text}" for text in known["evidence"]),
    ]
    if known["covers"]:
        lines += ["\nWHAT THEY COVER:", *(f"- {name}" for name in known["covers"])]
    if known["gap"]:
        lines += ["\nTHE GAP, IF IT IS WORTH A HALF-SENTENCE:", f"- {known['gap'][0]}"]
    if kind == "answer":
        lines += [f"\nTHE QUESTION:\n{question}"]
    return "\n".join(lines)


@router.post("/{application_id}/artifacts", status_code=201)
def write_artifact(
    application_id: int, body: ArtifactIn, session: SessionDep
) -> ArtifactOut:
    if body.kind not in KINDS:
        raise HTTPException(422, f"No such artifact as {body.kind!r}.")
    question = body.question.strip()
    if body.kind == "answer" and not question:
        raise HTTPException(422, "An answer needs the question it is answering.")

    row = session.get(Application, application_id)
    if row is None:
        raise HTTPException(404, "No such application.")
    if not row.selected_bullets:
        raise HTTPException(
            422,
            "No CV was generated for this posting, so there is no evidence to "
            "write from. Generate one first.",
        )

    choose(body.model)
    source = current_profile(session)
    profile = parse_text(source.text) if source else None
    known = facts(row, profile)

    answer = generate_json(
        _prompt(body.kind, question, known),
        SCHEMA,
        local="first",
        good=lambda written: bool(str(written.get("body") or "").strip()),
    )

    text = str(answer.get("body") or "").strip()
    flags: list[Flag] = []
    if profile:
        # The same guard the CV gets. It cannot catch an invented fact, which is
        # why the facts are chosen in code; it catches the words you never say.
        _check_banned(profile.rules, text, flags)

    made = ArtifactOut(
        kind=body.kind,
        question=question,
        subject=str(answer.get("subject") or "").strip(),
        body=text,
        model=served.get(),
        # stamp, not isoformat: a naive UTC string reads as local in the
        # browser, so a stamp four hours old rendered as "in 4 hours".
        created_at=stamp(now()) or "",
        flags=flags,
    )
    # Reassigned rather than appended: SQLModel does not see a mutated list.
    row.artifacts = [*row.artifacts, made.model_dump(exclude={"flags"})]
    session.add(row)
    session.commit()
    return made
