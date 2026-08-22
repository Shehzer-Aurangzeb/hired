"""
python -m app.seed_demo

The starter profile, plus four postings covering the states worth looking at, so the applications screens
have something real to render before the fit check and export exist.

ponytail: throwaway. Delete it once POST /api/applications has a real caller.
Refuses to run against a database that already has rows.
"""

from datetime import timedelta

from sqlmodel import Session, select

from .db import engine, init_db
from .models import ParsedJd
from .profile_template import template
from .tables import Application, ProfileSource, now

ROWS = [
    dict(
        company="Air Canada",
        role="Front End Developer",
        source="LinkedIn",
        fit_score=8,
        fit_reasoning="React and TypeScript throughout, and the BFF work lines up.",
        gaps=["Kubernetes"],
        required=[("React", 3), ("TypeScript", 3), ("Kubernetes", 2)],
        preferred=[("Next.js", 2)],
        status="applied",
        days_ago=3,
        pdf=b"%PDF-1.4 placeholder",
        filename="Shehzar_Abbasi_AirCanada_FrontEndDeveloper.pdf",
        title_variant="frontend",
        summary_text="Front-end engineer with 3.5+ years in TypeScript.",
        selected_bullet_ids=["dedicate-frontend-scratch", "dedicate-caching"],
    ),
    dict(
        company="Shopify",
        role="Senior Staff Engineer",
        source="Company site",
        fit_score=3,
        fit_reasoning="Ten years and org-level ownership. Two levels above.",
        gaps=["Team leadership at scale", "Distributed systems", "Ruby"],
        required=[("Ruby", 3), ("Distributed systems", 3), ("Team leadership at scale", 3)],
        preferred=[("GraphQL", 1)],
        # The record this whole design exists for: kept for the gaps, no CV.
        status="skipped",
        days_ago=9,
    ),
    dict(
        company="Lightspeed",
        role="Full-Stack Developer",
        source="Recruiter",
        fit_score=7,
        fit_reasoning="Node and Postgres match. GraphQL is thin.",
        gaps=["GraphQL federation"],
        required=[("Node.js", 3), ("PostgreSQL", 2), ("GraphQL federation", 2)],
        preferred=[("Docker", 1)],
        status="saved",
        days_ago=1,
    ),
    dict(
        company="Coveo",
        role="Frontend Engineer",
        fit_score=8,
        fit_reasoning="Design systems work is a direct match.",
        gaps=[],
        required=[("React", 3), ("Design systems", 3)],
        preferred=[("Storybook", 2)],
        status="interview",
        days_ago=21,
        pdf=b"%PDF-1.4 placeholder",
        filename="Shehzar_Abbasi_Coveo_FrontendEngineer.pdf",
        title_variant="frontend",
        summary_text="Front-end engineer with 3.5+ years in TypeScript.",
        selected_bullet_ids=["dedicate-frontend-scratch"],
    ),
]


def main() -> None:
    init_db()
    with Session(engine) as session:
        if session.exec(select(Application)).first():
            raise SystemExit("Applications already exist. Refusing to add demo rows on top.")

        # The screens need a profile before the guards let you near them.
        if not session.exec(select(ProfileSource)).first():
            session.add(ProfileSource(text=template()))
            print("Seeded the starter profile.")

        for row in ROWS:
            days = row.pop("days_ago")
            required = row.pop("required")
            preferred = row.pop("preferred")
            created = now() - timedelta(days=days)
            session.add(
                Application(
                    **row,
                    jd_text=f"Job description for {row['company']}, pasted in full.",
                    jd_parsed=ParsedJd(
                        company=row["company"],
                        role=row["role"],
                        location="Montreal, QC",
                        work_mode="Hybrid",
                        required_skills=[{"name": n, "importance": i} for n, i in required],
                        preferred_skills=[{"name": n, "importance": i} for n, i in preferred],
                        keywords=[n.lower() for n, _ in required],
                    ).model_dump(),
                    created_at=created,
                    applied_at=created if row["status"] not in ("saved", "skipped") else None,
                )
            )
        session.commit()
        print(f"Inserted {len(ROWS)} demo applications.")


if __name__ == "__main__":
    main()
