"""CRUD routes for saved job applications and their generated CV PDFs."""

import re

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel
from sqlmodel import select

from .db import SessionDep
from .models import ParsedJd
from .tables import SENT, STATUSES, Application, now, stamp

router = APIRouter(prefix="/applications", tags=["applications"])


class ApplicationIn(BaseModel):
    """Fit check plus CV step output. Export attaches the PDF later."""

    company: str
    role: str
    source: str | None = None
    url: str | None = None

    jd_text: str
    jd_parsed: ParsedJd = ParsedJd()
    fit_score: int
    fit_reasoning: str = ""
    gaps: list[str] = []
    fit_model: str = ""

    title_variant: str | None = None
    summary_text: str | None = None
    selected_bullet_ids: list[str] = []
    selected_bullets: list[dict] = []
    coverage: list[dict] = []

    status: str = "saved"
    notes: str | None = None


class ApplicationOut(BaseModel):
    """Everything but the PDF bytes, which come from the /pdf route."""

    id: int
    company: str
    role: str
    source: str | None
    url: str | None

    jd_text: str
    jd_parsed: ParsedJd
    fit_score: int
    fit_reasoning: str
    gaps: list[str]
    # Which model read the posting and scored it.
    fit_model: str = ""

    title_variant: str | None
    summary_text: str | None
    selected_bullet_ids: list[str]
    selected_bullets: list[dict]
    coverage: list[dict]
    # Which model chose the bullets on the saved PDF.
    model: str = ""
    # Emails and form answers written for this posting, newest last.
    artifacts: list[dict] = []

    has_pdf: bool
    filename: str | None

    status: str
    applied_at: str | None
    created_at: str
    notes: str | None

    @classmethod
    def of(cls, row: Application) -> "ApplicationOut":
        return cls(
            **row.model_dump(exclude={"pdf", "applied_at", "created_at"}),
            has_pdf=row.pdf is not None,
            applied_at=stamp(row.applied_at),
            created_at=stamp(row.created_at) or "",
        )


class ApplicationPatch(BaseModel):
    """Only status and notes are editable; the rest records what was sent."""

    status: str | None = None
    notes: str | None = None


def _check_status(status: str) -> None:
    if status not in STATUSES:
        raise HTTPException(422, f"Unknown status '{status}'. One of: {', '.join(STATUSES)}.")


def _get(session: SessionDep, application_id: int) -> Application:
    row = session.get(Application, application_id)
    if row is None:
        raise HTTPException(404, "No such application.")
    return row


@router.get("")
def list_applications(session: SessionDep) -> list[ApplicationOut]:
    rows = session.exec(select(Application).order_by(Application.created_at.desc())).all()
    return [ApplicationOut.of(row) for row in rows]


@router.post("", status_code=201)
def create_application(body: ApplicationIn, session: SessionDep) -> ApplicationOut:
    _check_status(body.status)
    row = Application(**body.model_dump())
    if body.status in SENT:
        row.applied_at = now()
    session.add(row)
    session.commit()
    session.refresh(row)
    return ApplicationOut.of(row)


@router.get("/{application_id}")
def get_application(application_id: int, session: SessionDep) -> ApplicationOut:
    return ApplicationOut.of(_get(session, application_id))


@router.patch("/{application_id}")
def patch_application(
    application_id: int, body: ApplicationPatch, session: SessionDep
) -> ApplicationOut:
    row = _get(session, application_id)
    changed = body.model_fields_set

    if "status" in changed and body.status is not None:
        _check_status(body.status)
        row.status = body.status
        # Stamped once, so re-entering the pipeline keeps the real date.
        if body.status in SENT and row.applied_at is None:
            row.applied_at = now()

    if "notes" in changed:
        # fields_set, not a None check, so an explicit null clears the notes.
        row.notes = body.notes

    session.add(row)
    session.commit()
    session.refresh(row)
    return ApplicationOut.of(row)


@router.delete("/{application_id}", status_code=204)
def delete_application(application_id: int, session: SessionDep) -> Response:
    session.delete(_get(session, application_id))
    session.commit()
    return Response(status_code=204)


@router.get("/{application_id}/pdf")
def get_pdf(application_id: int, session: SessionDep) -> Response:
    row = _get(session, application_id)
    if row.pdf is None:
        raise HTTPException(404, "No CV was generated for this application.")
    return Response(
        content=row.pdf,
        media_type="application/pdf",
        # inline so the in-app viewer renders it.
        headers={"Content-Disposition": f'inline; filename="{_safe(row.filename)}"'},
    )


def _safe(name: str | None) -> str:
    # Stops header injection via the filename.
    return re.sub(r"[^A-Za-z0-9._-]", "_", name or "cv.pdf")
