"""
The CV, as HTML and then as a PDF.

Jinja renders it and Chromium prints it, which means what you see in the preview
is what comes out: one layout engine, not two. No model is anywhere near this
step. The sentences were already chosen by the time anything gets here.
"""

import math
import re
from datetime import date
from pathlib import Path

from fastapi import HTTPException
from jinja2 import Environment, FileSystemLoader, select_autoescape

from .models import GeneratedCv, Profile
from .settings import get_settings

TEMPLATES = Path(__file__).parent / "templates"

# Letter at 96dpi, less the half-inch margins the stylesheet declares. The
# stylesheet is the source of truth; these have to be changed together.
PAGE_HEIGHT = int((11 - 1.0) * 96)

_env = Environment(
    loader=FileSystemLoader(TEMPLATES),
    autoescape=select_autoescape(["html"]),
    trim_blocks=True,
    lstrip_blocks=True,
)


def _url(value: str) -> str:
    """
    Profiles are written "github.com/you", and a PDF reader hands a href with no
    scheme to the operating system as a file path, which does nothing. Anything
    that already carries a scheme, mailto: included, is left alone.
    """
    return value if re.match(r"^[a-z][a-z0-9+.-]*:", value or "", re.I) else f"https://{value}"


_env.filters["url"] = _url


def render_html(profile: Profile, cv: GeneratedCv) -> str:
    """
    The selected bullets, put back under the employers they came from.

    The selector answers in project ids and knows nothing about who you worked
    for; that structure lives in the profile, so it is rejoined here rather than
    asked for.
    """
    placed = {section.project_id: section for section in cv.sections}
    employment = []
    for employer in profile.experience:
        sections = [placed[p.id] for p in employer.projects if p.id in placed]
        if sections:
            employment.append(
                {
                    "name": employer.name,
                    "role": employer.role,
                    "location": employer.location,
                    "employment_type": employer.employment_type,
                    "start": employer.start,
                    "end": employer.end,
                    "sections": sections,
                }
            )
    standalone = [placed[p.id] for p in profile.projects if p.id in placed]

    # A project's own links live on the profile, not on the selector's answer,
    # so the name is linked from here. First one wins: a CV has room for the
    # store listing or the repo, not a list of both.
    project_links = {
        p.id: p.links[0].url for p in profile.all_projects() if p.id in placed and p.links
    }

    return _env.get_template("cv.html").render(
        identity=profile.identity,
        cv=cv,
        employment=employment,
        standalone=standalone,
        project_links=project_links,
        education=sorted(profile.education, key=lambda e: e.priority),
        # An in-progress course is not a certification, and printing one as
        # though it were is the fastest way to lose a room.
        certifications=[c for c in profile.certifications if c.status == "earned"],
    )


def to_pdf(html: str) -> tuple[bytes, int]:
    """
    Print it, and say how many pages it came to.

    ponytail: the page count is measured height over page height rather than
    read out of the PDF. Counting objects in the file means parsing it, and this
    number only has to answer "did it fit", which is the question the budget loop
    asks. Swap for pypdf the day the count needs to be exact.
    """
    from playwright.sync_api import Error, sync_playwright

    launch = {}
    if path := get_settings().chrome_path:
        launch["executable_path"] = path

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(**launch)
            try:
                page = browser.new_page()
                page.set_content(html, wait_until="load")
                page.emulate_media(media="print")
                height = page.evaluate("document.documentElement.scrollHeight")
                pdf = page.pdf(
                    format="Letter",
                    print_background=True,
                    margin={
                        "top": "0.5in",
                        "bottom": "0.5in",
                        "left": "0.5in",
                        "right": "0.5in",
                    },
                )
            finally:
                browser.close()
    except Error as error:
        # Almost always a browser that was never installed. Say which command.
        raise HTTPException(
            500,
            "Could not start the browser that prints the PDF. Run "
            f"`.venv/bin/playwright install chromium`. ({error.message.splitlines()[0]})",
        ) from error

    return pdf, max(1, math.ceil(height / PAGE_HEIGHT))


def filename(name: str, company: str, role: str, when: date | None = None) -> str:
    """
    Shehzar_Abbasi_AirCanada_FrontEndDeveloper_2026-08-23.pdf

    A recruiter's downloads folder is full of "resume.pdf", and the date is what
    tells you which version they actually received.
    """
    stamp = (when or date.today()).isoformat()
    parts = [_squash(name), _squash(company), _squash(role), stamp]
    return "_".join(part for part in parts if part) + ".pdf"


def _squash(text: str) -> str:
    """Title-cased and stripped to what a filesystem and a header both accept."""
    words = re.findall(r"[A-Za-z0-9]+", text or "")
    return "".join(word[:1].upper() + word[1:] for word in words)
