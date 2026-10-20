"""FastAPI app: middleware, profile and version routes, and the built frontend."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import APIRouter, Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
import difflib
from datetime import timedelta

from sqlmodel import select
from starlette.middleware.sessions import SessionMiddleware

from . import applications, artifacts, ask, auth, fit, generate
from .db import SessionDep, init_db
from .models import Profile, ValidationResult
from .profile_parser import ProfileError, parse_text, replace_bullet_text, validate_text
from .profile_template import claude_prompt, template
from .settings import get_settings
from .tables import VERSION_DAYS, VERSIONS_KEPT, ProfileSource, current_profile, now, stamp

settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    if settings.demo:
        import asyncio

        from . import demo
        from .db import engine

        # In a thread: seeding prints real PDFs, and Playwright's sync API
        # refuses to run inside the event loop this lifespan is running on.
        await asyncio.to_thread(demo.seed, engine)
    yield


# No /docs or /openapi.json: they would expose the API map without auth.
app = FastAPI(title="hired", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key,
    session_cookie="hired_session",
    max_age=settings.session_max_age,
    same_site=settings.cookie_samesite,
    https_only=settings.cookie_secure,
)
app.add_middleware(
    CORSMiddleware,
    # Credentialed CORS forbids a "*" origin.
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/demo")
def demo_mode() -> dict[str, bool]:
    """Unprotected, because the banner has to render before anyone signs in."""
    return {"demo": settings.demo}


@app.get("/api/health")
def health() -> dict[str, str]:
    # No session needed, so health probes work.
    return {"status": "ok"}


# Auth on the router so new routes cannot forget it.
api = APIRouter(prefix="/api", dependencies=[Depends(auth.require_session)])


@api.get("/profile/template")
def get_template() -> dict[str, str]:
    return {"text": template(), "claude_prompt": claude_prompt()}


@api.get("/profile", response_model=Profile)
def get_profile(session: SessionDep) -> Profile:
    row = _row(session)
    if row is None:
        raise HTTPException(404, "No profile saved yet.")
    return parse_text(row.text)


class SourceBody(BaseModel):
    text: str
    expected_updated_at: str | None = None


class TextBody(BaseModel):
    text: str


class RestoreBody(BaseModel):
    expected_updated_at: str | None = None


class BulletBody(BaseModel):
    text: str
    expected_updated_at: str | None = None


def _row(session: SessionDep) -> ProfileSource | None:
    """The newest version is the current profile."""
    return current_profile(session)


def _prune(session: SessionDep) -> None:
    """Drop versions older than VERSION_DAYS, but always keep the newest VERSIONS_KEPT."""
    keep = {
        row.id
        for row in session.exec(
            select(ProfileSource).order_by(ProfileSource.id.desc()).limit(VERSIONS_KEPT)
        ).all()
    }
    cutoff = now() - timedelta(days=VERSION_DAYS)
    for row in session.exec(select(ProfileSource).where(ProfileSource.updated_at < cutoff)):
        if row.id not in keep:
            session.delete(row)



def _source(row: ProfileSource | None) -> dict:
    return {
        "text": row.text if row else "",
        "exists": row is not None,
        "updated_at": stamp(row.updated_at) if row else None,
        "version": row.id if row else None,
    }


@api.get("/profile/source")
def get_source(session: SessionDep) -> dict:
    return _source(_row(session))


@api.post("/profile/validate")
def post_validate(body: TextBody) -> ValidationResult:
    return validate_text(body.text)


@api.patch("/profile/bullets/{bullet_id}")
def patch_bullet(bullet_id: str, body: BulletBody, session: SessionDep):
    # Reuses put_source so validation and the conflict check still apply.
    row = _row(session)
    if row is None:
        raise HTTPException(404, "No profile saved yet.")
    if not body.text.strip():
        raise HTTPException(422, "A bullet cannot be empty. Delete it in the source instead.")

    try:
        text = replace_bullet_text(row.text, bullet_id, body.text)
    except ProfileError as error:
        raise HTTPException(404, error.message) from error

    return put_source(
        SourceBody(text=text, expected_updated_at=body.expected_updated_at), session
    )


@api.put("/profile/source")
def put_source(body: SourceBody, session: SessionDep):
    result = validate_text(body.text)
    if not result.ok:
        return JSONResponse(
            {
                "detail": "The profile did not parse.",
                "errors": [issue.model_dump() for issue in result.errors],
            },
            status_code=422,
        )

    row = _row(session)
    # Reject saves made against a stale copy.
    if row is not None and body.expected_updated_at != stamp(row.updated_at):
        return JSONResponse(
            {
                "detail": "This profile changed somewhere else since you opened it.",
                **_source(row),
            },
            status_code=409,
        )

    # Append-only: every save is a new version row.
    fresh = ProfileSource(text=body.text, updated_at=now())
    session.add(fresh)
    _prune(session)
    session.commit()
    session.refresh(fresh)
    return _source(fresh)


class Version(BaseModel):
    """A saved version's metadata, without its text."""

    version: int
    updated_at: str
    chars: int
    current: bool


@api.get("/profile/versions")
def list_versions(session: SessionDep) -> list[Version]:
    rows = session.exec(select(ProfileSource).order_by(ProfileSource.id.desc())).all()
    return [
        Version(
            version=row.id,
            updated_at=stamp(row.updated_at) or "",
            chars=len(row.text),
            current=index == 0,
        )
        for index, row in enumerate(rows)
    ]


@api.get("/profile/versions/{version}")
def get_version(version: int, session: SessionDep) -> dict:
    row = session.get(ProfileSource, version)
    if row is None:
        raise HTTPException(404, "No such version. It may have been pruned.")
    return _source(row)


class DiffLine(BaseModel):
    # "+" added, "-" removed, " " unchanged context, "@" a jump between hunks.
    op: str
    text: str


class Diff(BaseModel):
    from_version: int
    to_version: int
    added: int
    removed: int
    lines: list[DiffLine]


@api.get("/profile/versions/{version}/diff")
def diff_version(version: int, session: SessionDep) -> Diff:
    """What restoring this version would change: "-" is lost, "+" comes back."""
    old = session.get(ProfileSource, version)
    current = _row(session)
    if old is None or current is None:
        raise HTTPException(404, "No such version. It may have been pruned.")

    lines = [
        DiffLine(op=line[0], text=line)
        for line in difflib.unified_diff(
            current.text.splitlines(), old.text.splitlines(), lineterm="", n=3
        )
        if not line.startswith(("---", "+++"))
    ]
    return Diff(
        from_version=current.id,
        to_version=version,
        added=sum(1 for line in lines if line.op == "+"),
        removed=sum(1 for line in lines if line.op == "-"),
        lines=lines,
    )


@api.post("/profile/versions/{version}/restore")
def restore_version(version: int, body: RestoreBody, session: SessionDep):
    """Restore by appending the old text as a new version, via the normal save path."""
    row = session.get(ProfileSource, version)
    if row is None:
        raise HTTPException(404, "No such version. It may have been pruned.")
    return put_source(
        SourceBody(text=row.text, expected_updated_at=body.expected_updated_at), session
    )


api.include_router(applications.router)
api.include_router(artifacts.router)
api.include_router(ask.router)
api.include_router(fit.router)
api.include_router(generate.router)

app.include_router(auth.router)
app.include_router(api)


# Serve the SPA from the same origin so the cookie works with SameSite=Lax.
# Mounted last so it cannot shadow /api; skipped when there is no build.
BUNDLE = Path(__file__).resolve().parents[2] / "frontend/dist/hired/browser"

if BUNDLE.is_dir():

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        # Unknown paths fall back to index.html so deep links work.
        candidate = (BUNDLE / path).resolve()
        # Must stay inside the bundle, or /../../.env becomes readable.
        if path and candidate.is_file() and candidate.is_relative_to(BUNDLE):
            return FileResponse(candidate)
        return FileResponse(BUNDLE / "index.html")

    app.mount("/", StaticFiles(directory=BUNDLE), name="bundle")
