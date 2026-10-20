"""Database tables (profile versions, applications) and UTC timestamp helpers."""

from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, Column, LargeBinary
from sqlmodel import JSON, Field, SQLModel

STATUSES = ("saved", "skipped", "applied", "replied", "interview", "rejected", "offer")

SENT = ("applied", "replied", "interview", "rejected", "offer")


def now() -> datetime:
    """Naive UTC, since SQLite drops tzinfo; stamp() adds it back."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def stamp(value: datetime | None) -> str | None:
    """ISO string marked UTC, so browsers do not read it as local time."""
    return value.replace(tzinfo=timezone.utc).isoformat() if value else None


# Versions older than VERSION_DAYS are pruned, but the newest VERSIONS_KEPT always stay.
VERSION_DAYS = 60
VERSIONS_KEPT = 5


class ProfileSource(SQLModel, table=True):
    """The master profile as an append-only log; the newest row is current."""

    __tablename__ = "profile_source"
    # AUTOINCREMENT so pruned ids are never reused; a reused id would make
    # restore fetch the wrong version.
    __table_args__ = {"sqlite_autoincrement": True}

    id: int | None = Field(default=None, primary_key=True)
    text: str
    updated_at: datetime = Field(default_factory=now)


class Application(SQLModel, table=True):
    """One saved job posting; CV columns are nullable since skipped ones have none."""

    __table_args__ = (
        CheckConstraint(
            "status IN ('" + "', '".join(STATUSES) + "')", name="application_status"
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    company: str
    role: str
    # jd_text keeps a copy because postings get taken down.
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
    # Snapshot as printed, not linked to the current profile.
    selected_bullets: list[dict] = Field(default_factory=list, sa_column=Column(JSON))
    coverage: list[dict] = Field(default_factory=list, sa_column=Column(JSON))
    # Which model read the posting and scored it. Saved with the row, so a
    # score can be compared against the model that produced it later.
    fit_model: str = ""
    # Which model chose these bullets. Stamped at export, so the page you kept
    # says what made it rather than what is configured today.
    model: str = ""

    # Emails and form answers written for this posting, newest last. On the row
    # rather than in a table of their own: they are read with their application
    # and never queried across. {kind, question, subject, body, model, created_at}
    artifacts: list[dict] = Field(default_factory=list, sa_column=Column(JSON))

    # Stored as bytes so the database is the only file to back up.
    pdf: bytes | None = Field(default=None, sa_column=Column(LargeBinary, nullable=True))
    filename: str | None = None

    status: str = "saved"
    applied_at: datetime | None = None
    created_at: datetime = Field(default_factory=now)
    notes: str | None = None


def current_profile(session) -> "ProfileSource | None":
    """
    The profile in use: the newest row. profile_source is an append-only log, so
    an unordered first() returns v1 and silently scores against an old file.
    """
    from sqlmodel import select

    return session.exec(select(ProfileSource).order_by(ProfileSource.id.desc())).first()
