"""App settings, read from HIRED_* env vars and backend/.env."""

from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="HIRED_",
        env_file=Path(__file__).resolve().parents[1] / ".env",
        extra="ignore",
    )

    database_url: str = "sqlite:///./hired.db"

    # No default: a shipped secret would let anyone forge sessions.
    secret_key: str

    # From `python -m app.hash_password`. Empty refuses every login.
    password_hash: str = ""

    cookie_secure: bool = False
    # Cross-site needs "none", which browsers only honour with cookie_secure.
    cookie_samesite: str = "lax"
    session_max_age: int = 60 * 60 * 24 * 14

    cors_origins: list[str] = ["http://localhost:4200"]

    gemini_api_key: str = Field(
        "", validation_alias=AliasChoices("HIRED_GEMINI_API_KEY", "GEMINI_API_KEY")
    )
    chrome_path: str = ""

    # Configurable because Google retires model names.
    gemini_model: str = "gemini-3.6-flash"

    # Runs on this Mac, so it has no quota and never routes to a stranger's
    # model. Measured at 90% requirement recall against Gemini's 49% on the same
    # eight postings, at ~39s a call against ~4s.
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "granite3.3:8b"

    # Fabricated profile, fabricated history, canned model answers. The database
    # has to be in memory, checked below, so a demo cannot write over real data.
    demo: bool = False

    # Empty uses the defaults in profile_template.py.
    profile_template: str = ""
    claude_briefing: str = ""



@lru_cache
def get_settings() -> Settings:
    settings = Settings()  # pyright: ignore[reportCallIssue]
    # Here rather than only in the launcher, because the launcher can be
    # bypassed and seeding demo applications over real ones cannot be undone.
    if settings.demo and settings.database_url not in ("sqlite://", "sqlite:///:memory:"):
        raise SystemExit(
            f"HIRED_DEMO is set but the database is {settings.database_url}. "
            "Demo mode only runs in memory, so it cannot touch real data."
        )
    return settings
