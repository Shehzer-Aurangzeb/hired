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

    openrouter_api_key: str = Field(
        "",
        validation_alias=AliasChoices(
            "HIRED_OPENROUTER_API_KEY", "OPENROUTER_API_KEY", "OPEN_ROUTER_API_KEY"
        ),
    )

    # Empty uses the defaults in profile_template.py.
    profile_template: str = ""
    claude_briefing: str = ""



@lru_cache
def get_settings() -> Settings:
    return Settings()  # pyright: ignore[reportCallIssue]
