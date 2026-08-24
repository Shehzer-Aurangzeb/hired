from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Read from the environment, prefixed HIRED_, with a .env file for local work.
    See .env.example for how to produce the two secrets.
    """

    # The path is absolute on purpose: a relative env_file resolves against the
    # working directory, so the app would only start when launched from backend/.
    model_config = SettingsConfigDict(
        env_prefix="HIRED_",
        env_file=Path(__file__).resolve().parents[1] / ".env",
        extra="ignore",
    )

    # sqlite:///./hired.db locally. A Postgres URL works unchanged, which is the
    # whole reason this is a setting and not a constant.
    database_url: str = "sqlite:///./hired.db"

    # Signs the session cookie. Required, and deliberately without a default: a
    # shipped default secret key is a forged session for anyone who reads GitHub.
    secret_key: str

    # scrypt output from `python -m app.hash_password`. Empty means no password
    # has been set, and every login is refused rather than let through.
    password_hash: str = ""

    # Cookie flags. Both change between localhost and a real deployment, which is
    # what makes them settings rather than literals.
    cookie_secure: bool = False
    # "lax" is right when the API and the frontend share a site. Cross-site needs
    # "none", which browsers only honour together with cookie_secure.
    cookie_samesite: str = "lax"
    session_max_age: int = 60 * 60 * 24 * 14

    cors_origins: list[str] = ["http://localhost:4200"]

    # Google AI Studio. GEMINI_API_KEY is the name Google's own tooling uses, so
    # both spellings are accepted rather than making a working key look missing.
    # Empty means every model-backed route answers 503 instead of half working.
    gemini_api_key: str = Field(
        "", validation_alias=AliasChoices("HIRED_GEMINI_API_KEY", "GEMINI_API_KEY")
    )
    # Empty uses the browser `playwright install chromium` puts in its own cache.
    # Set it when a deployment already has a Chromium and a second copy is 150MB
    # of image for nothing.
    chrome_path: str = ""

    # A setting because the free tier's limits move and the right model with them.
    # gemini-2.5-flash is retired for new keys and 404s with a note pointing here.
    gemini_model: str = "gemini-3.6-flash"

    # Content, not code. Empty means "use the default in app/profile_template.py",
    # so a fresh checkout needs no config and a reword needs no deploy of code.
    profile_template: str = ""
    claude_briefing: str = ""



@lru_cache
def get_settings() -> Settings:
    return Settings()  # pyright: ignore[reportCallIssue]  # values come from env
