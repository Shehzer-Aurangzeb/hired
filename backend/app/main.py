from contextlib import asynccontextmanager

from fastapi import APIRouter, Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlmodel import select
from starlette.middleware.sessions import SessionMiddleware

from . import applications, auth
from .db import SessionDep, init_db
from .models import Profile, ValidationResult
from .profile_parser import parse_text, validate_text
from .profile_template import claude_prompt, template
from .settings import get_settings
from .tables import ProfileSource, now, stamp

settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(title="hired", lifespan=lifespan)

# Signed, httpOnly, and nothing readable by script. Outermost so it wraps every
# route, including the auth ones that write to it.
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
    # The session is an httpOnly cookie, so every request carries credentials.
    # That also forbids a wildcard origin, which is why this list is explicit.
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# One dependency on the router rather than one per route: a route added later
# cannot forget to be protected, because there is nowhere unprotected to put it.
api = APIRouter(prefix="/api", dependencies=[Depends(auth.require_session)])


@api.get("/profile/template")
def get_template() -> dict[str, str]:
    """The starter file, and the briefing that hands it to Claude."""
    return {"text": template(), "claude_prompt": claude_prompt()}


@api.get("/profile", response_model=Profile)
def get_profile(session: SessionDep) -> Profile:
    # ponytail: re-parsed per request. A 30KB document is sub-millisecond, so
    # there is no cache and therefore no cache to invalidate on save.
    row = _row(session)
    if row is None:
        raise HTTPException(404, "No profile saved yet.")
    return parse_text(row.text)


# ---------- the profile source ----------


class SourceBody(BaseModel):
    text: str
    # The updated_at the editor was opened with. None means "I believe there is
    # nothing saved yet".
    expected_updated_at: str | None = None


class TextBody(BaseModel):
    text: str


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
    # A save composed against an older copy would overwrite whatever landed in
    # between. Sending no token while a profile exists is the same mistake made
    # by a client that did not know there was one.
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

app.include_router(auth.router)
app.include_router(api)
