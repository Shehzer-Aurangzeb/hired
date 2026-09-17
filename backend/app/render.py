"""
The CV, as HTML and then as a PDF. Jinja renders it and Chromium prints it, so
preview and print come off one layout engine. No model is near this step.
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

# A quarter inch every side, on Letter. Inches, because page.pdf refuses points.
MARGIN_IN = 0.25
MARGIN = {side: f"{MARGIN_IN}in" for side in ("top", "bottom", "left", "right")}
CONTENT_WIDTH_PT = (8.5 - 2 * MARGIN_IN) * 72

# Letter at 96dpi less the vertical margins, for the "did it fit" measurement.
PAGE_HEIGHT = int((11 - 2 * MARGIN_IN) * 96)

_env = Environment(
    loader=FileSystemLoader(TEMPLATES),
    autoescape=select_autoescape(["html"]),
    trim_blocks=True,
    lstrip_blocks=True,
)


@lru_cache(maxsize=1)
def _font_css() -> str:
    """Embedded, not named: a fallback to Helvetica would reflow the page."""
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
    """Add https:// when absent. A PDF reader reads a bare host as a file path."""
    return value if re.match(r"^[a-z][a-z0-9+.-]*:", value or "", re.I) else f"https://{value}"


def _month(value: str) -> str:
    """2024-11 to Nov 2024. Anything that is not a YYYY-MM passes through."""
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
    Hyperlink any link label the description names, and say whether any matched,
    since a label that absorbed them does not want them on the project name too.

    ponytail: first-occurrence replace, longest label first.
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
    """Selected bullets, refiled under employers. The selector only knows ids."""
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

    # A label that names its links gets those words linked; otherwise the name.
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
        content_width_pt=CONTENT_WIDTH_PT,
        font_css=_font_css(),
        identity=profile.identity,
        cv=cv,
        employment=employment,
        standalone=standalone,
        project_links=project_links,
        project_labels=project_labels,
        education=sorted(profile.education, key=lambda e: e.priority),
    )


@contextmanager
def measurer():
    """Yields html -> page count. One browser, because the fill loop asks often."""
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
    ponytail: the page count is measured height over page height, not read out
    of the PDF, since it only has to answer "did it fit".
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
        # Only a launch failure has an install fix. This message once hid a bad
        # pdf() argument behind "run playwright install".
        if "executable doesn" in detail.lower() or "playwright install" in detail.lower():
            detail = f"{detail} Run `.venv/bin/playwright install chromium`."
        raise HTTPException(500, f"Could not print the PDF. {detail}") from error

    return pdf, max(1, math.ceil(height / PAGE_HEIGHT))


def filename(name: str, company: str, role: str, when: date | None = None) -> str:
    """Shehzar_Abbasi_AirCanada_FrontEndDeveloper_2026-08-23.pdf"""
    stamp = (when or date.today()).isoformat()
    parts = [_squash(name), _squash(company), _squash(role), stamp]
    return "_".join(part for part in parts if part) + ".pdf"


def _squash(text: str) -> str:
    words = re.findall(r"[A-Za-z0-9]+", text or "")
    return "".join(word[:1].upper() + word[1:] for word in words)
