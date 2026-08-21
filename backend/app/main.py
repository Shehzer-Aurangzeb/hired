from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import select
from starlette.middleware.sessions import SessionMiddleware

from .db import SessionDep, init_db
from .models import Profile
from .profile_parser import parse_text
from .profile_template import claude_prompt, template
from .settings import get_settings
from .tables import ProfileSource

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


@app.get("/api/profile/template")
def get_template() -> dict[str, str]:
    """The starter file, and the briefing that hands it to Claude."""
    return {"text": template(), "claude_prompt": claude_prompt()}


@app.get("/api/profile", response_model=Profile)
def get_profile(session: SessionDep) -> Profile:
    # ponytail: re-parsed per request. A 30KB document is sub-millisecond, so
    # there is no cache and therefore no cache to invalidate on save.
    row = session.exec(select(ProfileSource)).first()
    if row is None:
        raise HTTPException(404, "No profile saved yet.")
    return parse_text(row.text)
