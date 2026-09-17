"""Every setting, read from the environment with a .env file for local work."""

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

    # No default on purpose: a shipped one is a forged session for any reader.
    secret_key: str

    # scrypt output from `python -m app.hash_password`. Empty refuses every login.
    password_hash: str = ""

    cookie_secure: bool = False
    # "lax" while the API and frontend share an origin. Cross-site needs "none",
    # which browsers only honour together with cookie_secure.
    cookie_samesite: str = "lax"
    session_max_age: int = 60 * 60 * 24 * 14

    cors_origins: list[str] = ["http://localhost:4200"]

    # Both spellings, since GEMINI_API_KEY is what Google's tooling uses.
    gemini_api_key: str = Field(
        "", validation_alias=AliasChoices("HIRED_GEMINI_API_KEY", "GEMINI_API_KEY")
    )
    chrome_path: str = ""

    # A setting because the free tier's limits move, and retired names 404.
    gemini_model: str = "gemini-3.6-flash"

    # Tried before Gemini when set. All three spellings are accepted.
    openrouter_api_key: str = Field(
        "",
        validation_alias=AliasChoices(
            "HIRED_OPENROUTER_API_KEY", "OPENROUTER_API_KEY", "OPEN_ROUTER_API_KEY"
        ),
    )

    # Content, not code, so a reword needs no deploy.
    profile_template: str = ""
    claude_briefing: str = ""



@lru_cache
def get_settings() -> Settings:
    return Settings()  # pyright: ignore[reportCallIssue]  # values come from env
