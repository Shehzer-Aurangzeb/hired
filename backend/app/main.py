import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .models import Profile
from .profile_parser import parse

# Set HIRED_MASTER to run against tests/fixtures/master.md while the real one is
# still being written.
MASTER = Path(
    os.getenv("HIRED_MASTER") or Path(__file__).resolve().parents[1] / "profile" / "master.md"
)

app = FastAPI(title="hired")
app.add_middleware(
    CORSMiddleware,
    # The session is an httpOnly cookie, so every request carries credentials.
    # That also forbids a wildcard origin, which is why this list is explicit.
    allow_origins=["http://localhost:4200"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/profile", response_model=Profile)
def get_profile() -> Profile:
    # ponytail: re-parsed per request. A 30KB file is sub-millisecond, so there is
    # no cache and therefore no /api/profile/reload endpoint to keep in sync.
    return parse(MASTER)
