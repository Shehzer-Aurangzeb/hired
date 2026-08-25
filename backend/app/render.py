"""
The CV, as HTML and then as a PDF.

Jinja renders it and Chromium prints it, which means what you see in the preview
is what comes out: one layout engine, not two. No model is anywhere near this
step. The sentences were already chosen by the time anything gets here.
"""

import base64
import math
import re
from contextlib import contextmanager
from datetime import date
from functools import lru_cache
from pathlib import Path

from fastapi import HTTPException
from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup, escape

from .models import GeneratedCv, Profile
from .settings import get_settings

TEMPLATES = Path(__file__).parent / "templates"

# The page box, taken from the source document: 28.8pt top, 21.6pt bottom, 36pt
# each side, on Letter. Chromium is told these directly rather than reading an
# @page rule, so they live here and the template assumes them.
# In inches, because page.pdf refuses points: 28.8pt, 21.6pt, 36pt.
MARGIN = {"top": "0.4in", "bottom": "0.3in", "left": "0.5in", "right": "0.5in"}

# Letter at 96dpi less the vertical margins, for the "did it fit" measurement.
PAGE_HEIGHT = int((11 - (28.8 + 21.6) / 72) * 96)

_env = Environment(
    loader=FileSystemLoader(TEMPLATES),
    autoescape=select_autoescape(["html"]),
    trim_blocks=True,
    lstrip_blocks=True,
)


@lru_cache(maxsize=1)
def _font_css() -> str:
    """
    Inter, embedded rather than named.

    A `font-family: Inter` that falls back to Helvetica on a machine without it
    reflows the whole page, and the point of this template is that it comes out
    the same everywhere. These are the four faces lifted out of the source
    .docx, which is where the layout was measured from.
    """
    faces = {
        "Inter-regular.ttf": ("normal", 400),
        "Inter-italic.ttf": ("italic", 400),
        "Inter-bold.ttf": ("normal", 700),
        "Inter-boldItalic.ttf": ("italic", 700),
    }
    blocks = []
    for name, (style, weight) in faces.items():
        raw = (TEMPLATES / "fonts" / name).read_bytes()
        data = base64.b64encode(raw).decode()
        blocks.append(
            "@font-face{font-family:Inter;"
            f"font-style:{style};font-weight:{weight};"
            f"src:url(data:font/ttf;base64,{data}) format('truetype')}}"
        )
    return "".join(blocks)


def _url(value: str) -> str:
    """
    Profiles are written "github.com/you", and a PDF reader hands a href with no
    scheme to the operating system as a file path, which does nothing. Anything
    that already carries a scheme, mailto: included, is left alone.
    """
    return value if re.match(r"^[a-z][a-z0-9+.-]*:", value or "", re.I) else f"https://{value}"


def _month(value: str) -> str:
    """
    2024-11 -> Nov 2024, present -> Present. Profiles are written in sortable
    dates because the validator orders employers by them; a CV is read by a
    person. Anything that is not a YYYY-MM is passed through untouched.
    """
    text = str(value or "").strip()
    match = re.fullmatch(r"(\d{4})-(\d{1,2})", text)
    if not match:
        return text[:1].upper() + text[1:] if text else ""
    year, month = int(match.group(1)), int(match.group(2))
    names = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
             "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
    return f"{names[month - 1]} {year}" if 1 <= month <= 12 else text


def _linkify(text: str, links) -> tuple[Markup, bool]:
    """
    Hyperlink any of a project's link labels that its own description names.

    A label reading "live on App Store + Play Store" comes out with both phrases
    linked, so the wording lives in one place instead of being repeated as a row
    of bare URLs after the name. Returns whether anything was linked, because a
    label that absorbed the links does not also want them on the project name.

    ponytail: a plain first-occurrence replace, longest label first so a longer
    phrase is not eaten by a shorter one inside it. It would mangle a label whose
    text repeats a link label inside another link's URL; none do, and the fix if
    one ever does is to match on word boundaries.
    """
    out = escape(text or "")
    used = False
    for link in sorted(links, key=lambda item: len(item.label or ""), reverse=True):
        needle = str(escape(link.label or ""))
        if not link.label or needle not in str(out):
            continue
        anchor = Markup('<a href="{href}">{text}</a>').format(href=_url(link.url), text=link.label)
        out = Markup(str(out).replace(needle, str(anchor), 1))
        used = True
    return out, used


_env.filters["url"] = _url
_env.filters["month"] = _month


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
                    "show_type": bool(employer.employment_type)
                    and employer.employment_type != "full-time"
                    and employer.employment_type not in employer.name.lower(),
                    "start": employer.start,
                    "end": employer.end,
                    "sections": sections,
                }
            )
    standalone = [placed[p.id] for p in profile.projects if p.id in placed]

    # A project's own links live on the profile, not on the selector's answer, so
    # they are resolved here. A label that names its links ("live on App Store +
    # Play Store") gets those words linked; one that does not falls back to
    # linking the project name, first link only.
    by_project = {p.id: p.links for p in profile.all_projects()}
    project_labels: dict[str, Markup] = {}
    project_links: dict[str, str] = {}
    for section in cv.sections:
        links = by_project.get(section.project_id) or []
        label, used = _linkify(section.label, links)
        project_labels[section.project_id] = label
        if links and not used:
            project_links[section.project_id] = links[0].url

    return _env.get_template("cv.html").render(
        font_css=_font_css(),
        identity=profile.identity,
        cv=cv,
        employment=employment,
        standalone=standalone,
        project_links=project_links,
        project_labels=project_labels,
        # Certifications are deliberately not passed: they live in the profile
        # so the fit check knows the skills are there, and they have never been
        # on this CV.
        education=sorted(profile.education, key=lambda e: e.priority),
    )


@contextmanager
def measurer():
    """
    Yields html -> how many pages it comes to, on one browser.

    The fill loop asks this several times per generation, and launching Chromium
    per question costs more than the whole rest of the route. One page object,
    reset by set_content, answers all of them.
    """
    from playwright.sync_api import sync_playwright

    launch = {}
    if path := get_settings().chrome_path:
        launch["executable_path"] = path

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(**launch)
        try:
            page = browser.new_page()

            def pages(html: str) -> float:
                page.set_content(html, wait_until="load")
                page.emulate_media(media="print")
                return page.evaluate("document.documentElement.scrollHeight") / PAGE_HEIGHT

            yield pages
        finally:
            browser.close()


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
                    margin=MARGIN,
                )
            finally:
                browser.close()
    except Error as error:
        detail = error.message.splitlines()[0]
        # Only a launch failure has an install fix. Blaming a missing browser for
        # every Playwright error sends the reader to the wrong place, which is
        # worse than no advice: this message once hid a bad pdf() argument.
        if "executable doesn" in detail.lower() or "playwright install" in detail.lower():
            detail = f"{detail} Run `.venv/bin/playwright install chromium`."
        raise HTTPException(500, f"Could not print the PDF. {detail}") from error

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
