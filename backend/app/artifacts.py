"""
The email and the form answer, written from an application already scored.

The model is never asked what to say. Code works that out from the row — the
company, the strongest bullets for this posting, what the profile covers, the
gap — and the model only joins it into prose. That split is the one that fixed
the fit reasoning, where output went from eleven fabricated sentences to three
accurate ones the moment the facts arrived already decided.

See docs/artifacts.md for why, and for what this deliberately does not promise.
"""

import re

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

# Asked not to use these, granite used them anyway. A prompt is a request and a
# check is a rule, so they are matched on the stem: "passion" catches
# "passionate", which the profile's own banned list missed by one suffix.
TELLS = (
    "excit", "thrill", "passion", "delight", "deeply", "truly", "dive in",
    "leverag", "synerg", "robust", "cutting-edge", "innovat", "game-chang",
    "dynamic", "seamless", "spearhead", "proven track record",
    "hit the ground running", "perfect fit", "wealth of experience",
    "i am confident", "look forward to hearing", "utilis", "utiliz",
    "genuinely", "align", "resonate", "tangible impact",
    "a strong fit", "make a difference",
)
_TELL = re.compile(r"\b(" + "|".join(TELLS) + r")", re.I)


def tells(text: str) -> list[Flag]:
    """The register that makes writing read as a machine's. Flagged, not removed:
    a word in a quoted bullet may be the candidate's own."""
    return [
        Flag(type="warn", message=f'Reads as AI: "{found.group(0)}".')
        for found in dict.fromkeys(_TELL.finditer(text), None)
    ]


SCHEMA = {
    "type": "object",
    "properties": {"subject": {"type": "string"}, "body": {"type": "string"}},
    "required": ["subject", "body"],
}

# Examples beat adjectives: a model matches a sample's register far better than
# it follows a description of one. These are the candidate's own, from
# applications he wrote by hand.
#
# The facts in them belong to other postings. The rule below says so, because a
# model handed a good example will otherwise reuse its content.
VOICE = """HOW THEY WRITE

Plain, like they typed it in one sitting. Never corporate, never polished.
Short: an answer is two to four sentences, an email three to five. If a
sentence adds no fact and no personality, it is not in the draft.

Honest and direct. They would rather name a gap than inflate, and naming one
reads as confident rather than weak. Warm but never eager: no gushing, no
thanking them for the opportunity, no telling them what their company values.

Never: genuinely, passionate, thrilled, excited to leverage, align with my
goals, resonates with me. Never three adjectives in a row. Never their own
mission read back to them in their own words. Never open with a list of stack.

EXAMPLES OF THE VOICE. Match their register, length and rhythm. The facts in
them are from other applications and are not yours to reuse:

  Q: Why this company?
  A: Honestly, this is pretty much what I already do. I've worked remotely my
     whole career, and turning designs into clean, responsive sites that are
     fast and work across devices is my day to day. So a remote frontend role
     like this lines up well with what I'm good at.

  Q: Describe a feature you shipped.
  A: On Stanley Paden, a React Native app I shipped to both stores, I built the
     push notifications. It registers the device token when the app opens,
     fires on new content or a manual send from the CMS, and deep-links straight
     to the right screen when you tap it — so a notification about a new
     audiobook opens that audiobook, not just the home page.

  Q: The role wants hardware integration, which they have not done.
  A: Thanks for moving my application forward. I'm really interested in this one
     — the React Native side and the hardware integration part especially.
     That's not something I've done before, and it's exactly the kind of thing
     I'd like to get into. Happy to jump on a call whenever works.

  An email to a recruiter:
     Hi, thanks for taking a look — CV attached. Quick recap: 3.5 years in,
     mostly startup work across React, Next.js, React Native and Node/NestJS,
     and I've shipped a couple of apps to both stores. Open to mid frontend,
     mobile, or junior full-stack. Let me know if anything looks like a fit."""


EMAIL = """You are the candidate. Write the email in the first person, as them,
applying for this job. The CV is attached, so the email does not repeat it: it
gives a reason to open it.

Complete sentences in three short paragraphs. Never a list, never semicolons
strung together, never a summary of a CV.

  Line one: the role, and that the CV is attached. One sentence. Not "I am
            writing to apply", not "I am writing to express my interest", not
            "I hope this finds you well". Say what it is and move on.
  Then: the two or three specifics below, in their own words, numbers included.
        Those numbers are measured; do not round, soften or drop them.
  Last:  one plain closing line.

A subject line of under nine words naming the role.

Never write: excited, thrilled, passion, delighted, deeply, truly, dive in,
leverage, synergy, robust, cutting-edge, innovative, game-changing, dynamic,
seamless, spearheaded, "proven track record", "hit the ground running",
"perfect fit", "I am confident that", "I hope this finds you well".

You are given everything there is to say. Add no fact, no company research, no
flattery, and no claim about what the candidate enjoys or believes. If the gap
below is named, one honest half-sentence is better than silence; do not
apologise for it."""


ANSWER = """You are the candidate. Answer this application form question in the
first person, as them.

Answer the question that was asked, in its own terms, and stop. No greeting, no
sign-off, no restating the question back. Three or four sentences unless the
question plainly wants more.

- Lead with the answer, not with a wind-up.
- Support it with the specifics below, in their own words, numbers included.
  Those numbers are measured; do not round or soften them.
- A question about wanting the job is answered from two things only: what the
  company says about itself below, and what the candidate has done. Never
  describe the company's mission, values or focus in words it did not use, and
  never claim the candidate admires or believes anything. Naming the work
  honestly is the answer; inventing a feeling about it is the thing that reads
  as a machine.

Never write: excited, thrilled, passion, delighted, deeply, truly, dive in,
leverage, synergy, robust, cutting-edge, innovative, game-changing, dynamic,
seamless, spearheaded, "proven track record", "hit the ground running",
"perfect fit", "I am confident that".

You are given everything there is to say. Add no fact and no company research.
Leave the subject empty."""


class ArtifactIn(BaseModel):
    kind: str
    # Required for an answer, ignored for an email.
    question: str = ""
    # Which model to write it. Empty means the configured routing.
    model: str = ""
    # A draft to rewrite and what to change about it. Sent as real turns rather
    # than quoted in the prompt: a model treats what it said itself as its own,
    # and quoted text as background reading.
    draft: str = ""
    change: str = ""


class ArtifactOut(BaseModel):
    kind: str
    question: str = ""
    subject: str = ""
    body: str
    model: str = ""
    created_at: str = ""
    # Banned phrases that reached the text. The caller decides what to do.
    flags: list[Flag] = []


# "Acme is a …", "Acme builds …". A definitional sentence, which is what the
# company actually says about itself.
_ABOUT = re.compile(
    r"[^.]*\b{name}\b\s+(?:is|builds|makes|provides|powers|helps|delivers|develops)\b[^.]*\.",
    re.I,
)


def about(row: Application) -> str:
    """
    What the company says it does, or nothing.

    Not the first paragraph: half the postings open with the job board's own
    furniture — "Company logo for, Homebase. Reposted 11 hours ago" — or an ATS
    header, and handing that over as the company's self-description is worse
    than handing over nothing.
    """
    text = " ".join((row.jd_text or "").split())
    name = (row.company or "").strip()
    if not name:
        return ""
    found = re.search(_ABOUT.pattern.format(name=re.escape(name)), text, re.I)
    if not found:
        return ""
    # From the name itself: a posting rarely puts a full stop before it, so the
    # match otherwise reaches back through the title, the location and the ATS id.
    said = found.group(0)
    start = re.search(re.escape(name), said, re.I)
    return said[start.start() :].strip()[:400]


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
        # So "why this company" is answered from what the company said about
        # itself. Forbidding the topic did not work: asked why they wanted to
        # work at a school payments company, the model wrote about its "mission
        # of improving healthcare".
        "about": about(row),
        "candidate": profile.identity.name if profile else "",
        "summary": (row.summary_text or "").strip(),
        "company": row.company,
        "role": row.role,
        "evidence": [b["text"] for b in bullets],
        "covers": met[:6],
        "gap": (row.gaps or unmet)[:1],
        # Kept out of the email: see _prompt.
    }


def _prompt(kind: str, question: str, known: dict) -> str:
    head = EMAIL if kind == "email" else ANSWER
    lines = [
        VOICE,
        "",
        head,
        f"\nCANDIDATE: {known['candidate']}",
        *(
            [f"HOW THEY DESCRIBE THEMSELVES, IN THEIR OWN WORDS:\n{known['summary']}"]
            if known["summary"]
            else []
        ),
        f"COMPANY: {known['company']}",
        f"ROLE: {known['role']}",
        "\nTHE TWO OR THREE SPECIFICS, IN THEIR OWN WORDS:",
        *(f"- {text}" for text in known["evidence"]),
    ]
    if kind == "answer" and known["about"]:
        lines += [
            "\nWHAT THE COMPANY SAYS ABOUT ITSELF. This is the only thing you know"
            " about them, and you may not go past it:",
            known["about"],
        ]
    if known["covers"]:
        lines += ["\nWHAT THEY COVER:", *(f"- {name}" for name in known["covers"])]
    if known["gap"] and kind == "answer":
        # Only where a question may ask for it, and never as something to soften:
        # handed this for an email, the model wrote that the candidate had "some
        # foundational experience" with the thing they had just been told is a gap.
        lines += [
            "\nWHAT THEY DO NOT HAVE. Mention it only if the question asks, and"
            " then as a plain absence, never as partial or foundational experience:",
            f"- {known['gap'][0]}",
        ]
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

    change = body.change.strip()
    turns = (
        [("model", body.draft.strip()), ("user", f"{change}\n\nWrite it again.")]
        if body.draft.strip() and change
        else None
    )
    answer = generate_json(
        _prompt(body.kind, question, known),
        SCHEMA,
        turns=turns,
        local="first",
        good=lambda written: bool(str(written.get("body") or "").strip()),
    )

    text = str(answer.get("body") or "").strip()
    flags: list[Flag] = []
    if profile:
        # The same guard the CV gets. It cannot catch an invented fact, which is
        # why the facts are chosen in code; it catches the words you never say.
        _check_banned(profile.rules, text, flags)
    flags += tells(text)

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
