"""
Demo mode: a fabricated profile, a fabricated history, and canned model answers.

Everything here is invented. The point is to show the app to someone, or take
screenshots, without exposing a real profile or spending a rationed model call.

The database is in memory, so demo mode cannot write to anything that outlives
the process, and every launch starts clean. settings.py refuses to start if the
flag is on and the database URL points at a file.
"""

from datetime import timedelta
from pathlib import Path

from sqlmodel import Session, select

from .profile_parser import parse_text
from .tables import SENT, Application, ProfileSource, now

# Known, and printed on the way up. A demo nobody can sign into is not a demo.
PASSWORD = "demo"

PROFILE = Path(__file__).resolve().parents[2] / "landing/demo/master.md"

JD = """Senior Front-End Engineer, Payments Dashboard — Fernhill (Toronto, hybrid)

We're looking for a senior front-end engineer to own the merchant dashboard:
the screens where businesses see every payment, refund and payout.

What you'll do
- Build and maintain complex, data-dense React interfaces in TypeScript
- Keep large tables fast: thousands of rows, live updates, filters
- Contribute to and extend our design system
- Make accessibility a default, not an afterthought

What we're looking for
- 5+ years building production React applications
- Strong TypeScript
- Experience with data fetching and caching (React Query, SWR or similar)
- Experience with a design system or component library
- Nice to have: GraphQL, Playwright, React Native for our mobile app
"""

FIT = {
    "parsed_jd": {
        "company": "Fernhill",
        "role": "Senior Front-End Engineer",
        "seniority": "Senior",
        "location": "Toronto, ON",
        "work_mode": "Hybrid",
        "required_skills": [
            {"name": "React", "importance": 3},
            {"name": "TypeScript", "importance": 3},
            {"name": "Large table virtualisation", "importance": 3},
            {"name": "React Query or SWR", "importance": 2},
            {"name": "Design systems", "importance": 2},
            {"name": "Accessibility", "importance": 2},
        ],
        "preferred_skills": [
            {"name": "GraphQL", "importance": 1},
            {"name": "Playwright", "importance": 1},
            {"name": "React Native", "importance": 1},
        ],
        "years_required": 5,
    },
    "score": 8,
    "reasoning": (
        "Five years of React and TypeScript at expert level, and the Ledgerline "
        "virtualisation work is close to exactly what this team describes. The "
        "design system and accessibility bullets cover the rest of the core list. "
        "React Native is listed in your gaps, but here it is a nice-to-have."
    ),
    "gaps": ["React Native, for the mobile app (nice to have, listed in your gaps)"],
}

SELECTION = {
    "title_id": "frontend",
    "sections": [
        {
            "project_id": "ledgerline-app",
            "bullet_ids": [
                "ledgerline-virtual",
                "ledgerline-rebuild",
                "ledgerline-cache",
                "ledgerline-a11y",
            ],
        },
        {
            "project_id": "northwind-design-system",
            "bullet_ids": ["northwind-ds", "northwind-tokens", "northwind-tests", "northwind-docs"],
        },
        {"project_id": "ledgerline-reports", "bullet_ids": ["reports-graphql", "reports-export"]},
        {"project_id": "tidepool", "bullet_ids": ["tidepool-app", "tidepool-offline"]},
    ],
}

# What an email looks like when the facts arrive already decided: the posting's
# own role, two bullets from the CV, and the gap, with none of the register.
ARTIFACT = {
    "subject": "Senior Front-End Engineer, React and TypeScript",
    "body": (
        "I saw the Senior Front-End Engineer role at Fernhill and have attached my CV.\n\n"
        "Most of my five years has been on data-heavy React and TypeScript interfaces: "
        "I virtualised a transactions table so 50,000-row ledgers scroll smoothly, "
        "cutting p75 load time by 40%, and built a 40-component library in Storybook "
        "that six client projects now use.\n\n"
        "React Native is on my list rather than behind me, so the mobile work would be "
        "a first. Happy to talk through any of it."
    ),
}

ASK = {
    "reply": "Recorded Redux at working level on Ledgerline and Tidepool.",
    "questions": [],
    "changes": [
        {
            "op": "add_skill_evidence",
            "target": "Redux",
            "level": "working",
            "context": "professional",
            "evidence": ["ledgerline-app", "tidepool"],
        }
    ],
}

# (company, role, score, status, days ago, gaps)
#
# The four marked with a CV go through the real generate and export path at seed
# time, so the detail pages show an actual PDF rather than "no CV was generated".
# A demo whose main screen is empty is showing the wrong thing.
HISTORY = [
    # Today, so the target shows one slot filled rather than an empty row.
    ("Vantage Point", "Senior Front-End Engineer", 9, "applied", 0, []),
    ("Copperline", "Front-End Engineer", 9, "interview", 3, []),
    ("Halcyon Health", "Senior React Developer", 7, "applied", 5, ["HIPAA experience"]),
    ("Brightwater", "UI Engineer, Design Systems", 8, "replied", 8, []),
    ("Ostara Labs", "Full-Stack Engineer", 6, "applied", 11, ["Go", "Kafka"]),
    ("Pinecrest", "Mobile Engineer", 3, "skipped", 12, ["React Native", "Swift"]),
    ("Meridian Bank", "Front-End Developer", 7, "rejected", 16, ["Angular"]),
    ("Larkspur", "Senior Front-End Engineer", 8, "applied", 19, []),
    ("Tessellate", "Platform Engineer", 2, "skipped", 21, ["Kubernetes", "Terraform"]),
    ("Northgate", "Product Engineer", 7, "saved", 1, ["Rails"]),
]


def answer(schema: dict, prompt: str = "") -> dict:
    """
    Which canned reply this call wants, told apart by the schema it was given.
    Each caller owns its own schema, so no flag has to be threaded through.
    """
    properties = schema.get("properties", {})
    if "required_skills" in properties:  # reading the posting
        return FIT["parsed_jd"]
    if set(properties) == {"reasoning"}:  # the sentences under a counted score
        return {"reasoning": FIT["reasoning"]}
    if "title_id" in properties:
        return {"title_id": SELECTION["title_id"]}
    if "bullet_ids" in properties:
        # Asked one project at a time, and the prompt lists that project's ids.
        return {
            "bullet_ids": next(
                (s["bullet_ids"] for s in SELECTION["sections"] if s["bullet_ids"][0] in prompt),
                [],
            )
        }
    if set(properties) == {"subject", "body"}:  # an email or a form answer
        return ARTIFACT
    if "op" in properties:
        return {"op": ASK["changes"][0]["op"], "reply": ASK["reply"], "questions": []}
    if "changes" in properties:
        return {"changes": [{k: v for k, v in c.items() if k != "op"} for c in ASK["changes"]]}
    return FIT


def _attach_cv(session, row, profile) -> None:
    """
    Build and attach a real CV, the same way /api/export does. Nothing is faked
    below the model call: the selector's answer is canned, the page is rendered
    by the template and printed by Chromium, so the PDF is the genuine artefact.
    """
    from .generate import _assemble
    from .models import ParsedJd
    from .render import filename, render_html, to_pdf

    cv, _ = _assemble(profile, SELECTION, None, ParsedJd.model_validate(FIT["parsed_jd"]))
    pdf, _pages = to_pdf(render_html(profile, cv))

    row.pdf = pdf
    row.filename = filename(profile.identity.name, row.company)
    row.title_variant = cv.title
    row.summary_text = cv.summary
    row.selected_bullet_ids = [b.id for s in cv.sections for b in s.bullets]
    row.selected_bullets = [
        {"id": b.id, "text": b.text, "project_name": s.project_name}
        for s in cv.sections
        for b in s.bullets
    ]
    row.coverage = [item.model_dump() for item in cv.coverage]
    session.add(row)


def seed(engine) -> None:
    """
    Fill an empty database. Three profile versions, so History has a list and a
    real diff rather than a single row, and nine applications across the stages.
    """
    with Session(engine) as session:
        if session.exec(select(ProfileSource)).first():
            return

        text = PROFILE.read_text()
        older = text.replace("level: expert", "level: advanced", 1)
        oldest = older.replace("  - id: ledgerline-a11y\n", "", 1)
        for n, body in enumerate([oldest, older, text]):
            session.add(ProfileSource(text=body, updated_at=now() - timedelta(days=12 - n * 5)))

        session.commit()
        profile = parse_text(text)

        for company, role, score, status, days, gaps in HISTORY:
            when = now() - timedelta(days=days)
            row = Application(
                company=company,
                role=role,
                source="LinkedIn",
                jd_text=JD if status in SENT else f"{role} at {company}.",
                jd_parsed=FIT["parsed_jd"] if status in SENT else {"company": company, "role": role},
                fit_score=score,
                fit_reasoning=FIT["reasoning"] if status in SENT else "",
                gaps=gaps,
                status=status,
                created_at=when,
                applied_at=when if status not in ("saved", "skipped") else None,
            )
            session.add(row)
            # SENT is already "the application went out, whatever route it
            # took". Hand-listing the statuses missed rejected, and you cannot
            # be rejected from something you never sent.
            if status in SENT:
                session.commit()
                _attach_cv(session, row, profile)
        session.commit()
