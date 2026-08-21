from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Read from the environment, prefixed HIRED_, with a .env file for local work.
    See .env.example for how to produce the two secrets.
    """

    model_config = SettingsConfigDict(env_prefix="HIRED_", env_file=".env", extra="ignore")

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

    # Content, not code. Empty means "use the default in app/profile_template.py",
    # so a fresh checkout needs no config and a reword needs no deploy of code.
    profile_template: str = ""
    claude_briefing: str = ""



@lru_cache
def get_settings() -> Settings:
    return Settings()  # pyright: ignore[reportCallIssue]  # values come from env
