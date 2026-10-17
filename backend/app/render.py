"""Renders the CV to HTML with Jinja and prints it to PDF with Chromium."""

import base64
import math
import re
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path

from fastapi import HTTPException
from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup, escape

from .models import GeneratedCv, Profile
from .settings import get_settings

TEMPLATES = Path(__file__).parent / "templates"

# Quarter-inch margins on Letter. In inches because page.pdf rejects points.
MARGIN_IN = 0.25
MARGIN = {side: f"{MARGIN_IN}in" for side in ("top", "bottom", "left", "right")}
CONTENT_WIDTH_PT = (8.5 - 2 * MARGIN_IN) * 72

# Printable height in CSS px (96dpi), used to count pages.
PAGE_HEIGHT = int((11 - 2 * MARGIN_IN) * 96)

_env = Environment(
    loader=FileSystemLoader(TEMPLATES),
    autoescape=select_autoescape(["html"]),
    trim_blocks=True,
    lstrip_blocks=True,
)


@lru_cache(maxsize=1)
def _font_css() -> str:
    """Inter embedded as base64, so a font fallback can't reflow the page."""
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
    """Add https:// unless the link is http(s), mailto or tel. Blocks javascript:, file: and the like."""
    return value if re.match(r"^(https?://|mailto:|tel:)", value or "", re.I) else f"https://{value}"


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
    """Link the first occurrence of each link label in text, longest first.
    Also returns whether any matched."""
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
    """Render the CV, grouping selected projects under their employers."""
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

    # Link words inside the label if they match; otherwise link the project name.
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
    """Yield a function html -> page count, reusing one browser."""
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
    """Print to PDF. Page count is estimated from content height, not read from the PDF."""
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
        # Only suggest installing Chromium when the launch itself failed.
        if "executable doesn" in detail.lower() or "playwright install" in detail.lower():
            detail = f"{detail} Run `.venv/bin/playwright install chromium`."
        raise HTTPException(500, f"Could not print the PDF. {detail}") from error

    return pdf, max(1, math.ceil(height / PAGE_HEIGHT))


def filename(name: str, company: str) -> str:
    """e.g. Jane_Doe_Acme.pdf

    Whose CV and which company, nothing else. The role and the date pushed it
    past eighty characters, and neither tells the recruiter opening it anything
    the CV does not already say.
    """
    parts = [_squash(name), _squash(company)]
    return "_".join(part for part in parts if part) + ".pdf"


def _squash(text: str) -> str:
    words = re.findall(r"[A-Za-z0-9]+", text or "")
    return "".join(word[:1].upper() + word[1:] for word in words)
