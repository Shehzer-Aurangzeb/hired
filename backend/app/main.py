"""
App wiring: middleware, the profile routes, and the built frontend. Everything
under /api needs a session, and the bundle is served here, so one process.
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import APIRouter, Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from sqlmodel import select
from starlette.middleware.sessions import SessionMiddleware

from . import applications, auth, fit, generate
from .db import SessionDep, init_db
from .models import Profile, ValidationResult
from .profile_parser import ProfileError, parse_text, replace_bullet_text, validate_text
from .profile_template import claude_prompt, template
from .settings import get_settings
from .tables import ProfileSource, now, stamp

settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(title="hired", lifespan=lifespan)

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
    # Credentialed requests forbid a wildcard origin, so this list is explicit.
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, str]:
    """Unprotected on purpose: a platform probe has no session, and 401 reads as dead."""
    return {"status": "ok"}


# On the router, not per route, so a route added later cannot forget it.
api = APIRouter(prefix="/api", dependencies=[Depends(auth.require_session)])


@api.get("/profile/template")
def get_template() -> dict[str, str]:
    return {"text": template(), "claude_prompt": claude_prompt()}


@api.get("/profile", response_model=Profile)
def get_profile(session: SessionDep) -> Profile:
    # ponytail: re-parsed per request. A 30KB document is sub-millisecond, so
    # there is no cache to invalidate on save.
    row = _row(session)
    if row is None:
        raise HTTPException(404, "No profile saved yet.")
    return parse_text(row.text)


# ---------- the profile source ----------


class SourceBody(BaseModel):
    text: str
    expected_updated_at: str | None = None


class TextBody(BaseModel):
    text: str


class BulletBody(BaseModel):
    # Same lock as the editor: one row, so a bullet edit rewrites all of it.
    text: str
    expected_updated_at: str | None = None


def _row(session: SessionDep) -> ProfileSource | None:
    return session.exec(select(ProfileSource)).first()



def _source(row: ProfileSource | None) -> dict:
    return {
        "text": row.text if row else "",
        "exists": row is not None,
        "updated_at": stamp(row.updated_at) if row else None,
    }


@api.get("/profile/source")
def get_source(session: SessionDep) -> dict:
    return _source(_row(session))


@api.post("/profile/validate")
def post_validate(body: TextBody) -> ValidationResult:
    return validate_text(body.text)


@api.patch("/profile/bullets/{bullet_id}")
def patch_bullet(bullet_id: str, body: BulletBody, session: SessionDep):
    """Rewrites one line, then reuses the editor's save path for the checks."""
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
    # A save written against an older copy would overwrite what landed between.
    if row is not None and body.expected_updated_at != stamp(row.updated_at):
        return JSONResponse(
            {
                "detail": "This profile changed somewhere else since you opened it.",
                **_source(row),
            },
            status_code=409,
        )

    if row is None:
        row = ProfileSource(text=body.text)
    row.text = body.text
    row.updated_at = now()
    session.add(row)
    session.commit()
    session.refresh(row)
    return _source(row)


api.include_router(applications.router)
api.include_router(fit.router)
api.include_router(generate.router)

app.include_router(auth.router)
app.include_router(api)


# One origin keeps the session cookie on SameSite=Lax; two would need
# SameSite=None, which Safari and Brave refuse. Mounted last so it cannot
# shadow /api, and skipped with no build so `ng serve` is unaffected.

BUNDLE = Path(__file__).resolve().parents[2] / "frontend/dist/hired/browser"

if BUNDLE.is_dir():

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        """Anything that is not a real file is index.html, so deep links work."""
        candidate = (BUNDLE / path).resolve()
        # Must stay inside the bundle. Without this, /../../.env is a file read.
        if path and candidate.is_file() and candidate.is_relative_to(BUNDLE):
            return FileResponse(candidate)
        return FileResponse(BUNDLE / "index.html")

    app.mount("/", StaticFiles(directory=BUNDLE), name="bundle")
