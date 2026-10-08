# Captures the landing screenshots. Run: cd backend && .venv/bin/python ../landing/demo/capture.py
import os
import sys
import tempfile
import threading
import time
from datetime import timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "src" / "assets" / "shots"
BACKEND = HERE.parents[1] / "backend"
PORT = 8765
URL = f"http://127.0.0.1:{PORT}"
PASSWORD = "demo-password-for-screenshots"

# Must be set before importing the app, which reads settings at import time.
tmp = Path(tempfile.mkdtemp(prefix="hired-demo-"))
os.environ.update(
    HIRED_DATABASE_URL=f"sqlite:///{tmp / 'demo.db'}",
    HIRED_SECRET_KEY="demo-only-not-a-secret",
    HIRED_GEMINI_API_KEY="",
    HIRED_OPENROUTER_API_KEY="",
)
sys.path.insert(0, str(BACKEND))

from app.auth import hash_password  # noqa: E402

os.environ["HIRED_PASSWORD_HASH"] = hash_password(PASSWORD)

import uvicorn  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402
from sqlmodel import Session  # noqa: E402

from app import fit, generate  # noqa: E402
from app.db import engine, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.tables import Application, ProfileSource, now  # noqa: E402

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
            {"name": "Large data tables", "importance": 3},
            {"name": "Data fetching and caching", "importance": 2},
            {"name": "Design systems", "importance": 2},
            {"name": "Accessibility", "importance": 2},
        ],
        "preferred_skills": [
            {"name": "GraphQL", "importance": 1},
            {"name": "Playwright", "importance": 1},
            {"name": "React Native", "importance": 1},
        ],
        "keywords": ["payments", "dashboard", "merchant"],
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
    "coverage": [
        {"skill": "React", "bullet_ids": ["ledgerline-rebuild", "northwind-ds"]},
        {"skill": "TypeScript", "bullet_ids": ["ledgerline-rebuild"]},
        {"skill": "Large data tables", "bullet_ids": ["ledgerline-virtual"]},
        {"skill": "Data fetching and caching", "bullet_ids": ["ledgerline-cache"]},
        {"skill": "Design systems", "bullet_ids": ["northwind-ds"]},
        {"skill": "Accessibility", "bullet_ids": ["ledgerline-a11y"]},
        {"skill": "GraphQL", "bullet_ids": ["reports-graphql"]},
        {"skill": "Playwright", "bullet_ids": ["northwind-tests"]},
        {"skill": "React Native", "bullet_ids": []},
    ],
}


def fake_model(_prompt, schema):
    """Fake model call. The selector's schema is the one with title_id."""
    return SELECTION if "title_id" in schema["properties"] else FIT


fit.generate_json = fake_model
generate.generate_json = fake_model

# (company, role, score, status, days ago, gaps)
HISTORY = [
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


def seed_history() -> None:
    with Session(engine) as session:
        for company, role, score, status, days, gaps in HISTORY:
            when = now() - timedelta(days=days)
            session.add(
                Application(
                    company=company,
                    role=role,
                    source="LinkedIn",
                    jd_text=f"{role} at {company}.",
                    jd_parsed={"company": company, "role": role},
                    fit_score=score,
                    fit_reasoning="",
                    gaps=gaps,
                    status=status,
                    created_at=when,
                    applied_at=when if status not in ("saved", "skipped") else None,
                )
            )
        session.commit()


def seed_profile() -> None:
    with Session(engine) as session:
        session.add(ProfileSource(text=(HERE / "master.md").read_text()))
        session.commit()


def serve() -> None:
    init_db()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    for _ in range(100):
        if server.started:
            return
        time.sleep(0.1)
    raise SystemExit("demo server did not start")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    serve()
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=2)

        def shot(name: str, full: bool = False) -> None:
            page.wait_for_load_state("load")
            page.wait_for_timeout(1200)
            page.screenshot(path=OUT / f"{name}.png", full_page=full)
            print("wrote", name)

        page.goto(f"{URL}/login")
        page.fill("#password", PASSWORD)
        page.click("button[type=submit]")
        page.wait_for_url("**/setup")
        shot("setup")

        seed_profile()
        seed_history()

        page.goto(f"{URL}/generate")
        page.fill("textarea", JD)
        shot("paste")
        page.click("button:has-text('Check fit')")
        page.wait_for_selector("text=Generate a CV")
        shot("fit")

        with page.expect_response("**/api/generate") as generated:
            page.click("button:has-text('Generate a CV')")
        cv = generated.value.json()["cv"]
        page.wait_for_selector("button:has-text('Export')", timeout=60_000)
        page.wait_for_timeout(1500)  # the preview iframe renders after the result
        shot("generate")
        # Same template the PDF prints from, at Letter width (8.5in at 96dpi).
        html = page.request.post(f"{URL}/api/preview", data={"cv": cv}).text()
        sheet = browser.new_page(viewport={"width": 816, "height": 1056}, device_scale_factor=2)
        sheet.set_content(html)
        sheet.add_style_tag(content="html { padding: 0.25in; background: #fff }")  # the PDF margins
        sheet.wait_for_timeout(500)
        sheet.screenshot(path=OUT / "cv.png")
        sheet.close()
        print("wrote cv")

        page.goto(f"{URL}/applications")
        shot("applications")

        page.goto(f"{URL}/profile")
        shot("profile")

        browser.close()


if __name__ == "__main__":
    main()
