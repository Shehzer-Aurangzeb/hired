"""The two tables, and the UTC helpers every timestamp goes through."""

from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, Column, LargeBinary
from sqlmodel import JSON, Field, SQLModel

# Whether a PDF exists is a separate fact, so "generated" is not a stage.
STATUSES = ("saved", "skipped", "applied", "replied", "interview", "rejected", "offer")

SENT = ("applied", "replied", "interview", "rejected", "offer")


def now() -> datetime:
    """Naive UTC, because SQLite drops tzinfo anyway. stamp() puts it back."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def stamp(value: datetime | None) -> str | None:
    """UTC-marked ISO. A naive one is read as local time and shifts every date."""
    return value.replace(tzinfo=timezone.utc).isoformat() if value else None


class ProfileSource(SQLModel, table=True):
    """
    The master profile, as typed. One row, forever, in the database because a
    container filesystem is wiped on redeploy.
    """

    __tablename__ = "profile_source"
    __table_args__ = (CheckConstraint("id = 1", name="profile_source_single_row"),)

    id: int | None = Field(default=1, primary_key=True)
    text: str
    updated_at: datetime = Field(default_factory=now)


class Application(SQLModel, table=True):
    """
    One posting you kept, not one CV sent. The rows worth most are often the
    skipped ones, so every CV-shaped column below is nullable.
    """

    __table_args__ = (
        CheckConstraint(
            "status IN ('" + "', '".join(STATUSES) + "')", name="application_status"
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    company: str
    role: str
    # The URL alone is not enough: postings come down, so jd_text keeps a copy.
    source: str | None = None
    url: str | None = None

    jd_text: str
    jd_parsed: dict = Field(default_factory=dict, sa_column=Column(JSON))

    fit_score: int
    fit_reasoning: str
    gaps: list[str] = Field(default_factory=list, sa_column=Column(JSON))

    title_variant: str | None = None
    summary_text: str | None = None
    selected_bullet_ids: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    # As printed, not joined against today's profile: this is what they read.
    selected_bullets: list[dict] = Field(default_factory=list, sa_column=Column(JSON))
    # Judged at generation time, stored for the same reason as the text above.
    coverage: list[dict] = Field(default_factory=list, sa_column=Column(JSON))

    # The bytes, not a path, so the whole app stays one file to back up.
    pdf: bytes | None = Field(default=None, sa_column=Column(LargeBinary, nullable=True))
    filename: str | None = None

    status: str = "saved"
    applied_at: datetime | None = None
    created_at: datetime = Field(default_factory=now)
    notes: str | None = None
