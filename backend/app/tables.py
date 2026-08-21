from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, Column, LargeBinary
from sqlmodel import JSON, Field, SQLModel

STATUSES = ("generated", "applied", "replied", "interview", "rejected", "offer")


def now() -> datetime:
    return datetime.now(timezone.utc)


class ProfileSource(SQLModel, table=True):
    """
    The master profile, as the markdown you typed. One row, forever.

    It lives here rather than on disk because the app is deployed: a container
    filesystem is wiped on redeploy, and this is the only copy of the CV data.
    app/profile_parser.py turns this text into the parsed Profile the API serves.
    """

    __tablename__ = "profile_source"
    __table_args__ = (CheckConstraint("id = 1", name="profile_source_single_row"),)

    id: int | None = Field(default=1, primary_key=True)
    text: str
    updated_at: datetime = Field(default_factory=now)


class Application(SQLModel, table=True):
    """
    One CV sent to one employer. Written once at export, then only status and
    notes change.
    """

    __table_args__ = (
        CheckConstraint(
            "status IN ('" + "', '".join(STATUSES) + "')", name="application_status"
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    company: str
    role: str
    source: str | None = None

    jd_text: str
    jd_parsed: dict = Field(default_factory=dict, sa_column=Column(JSON))

    fit_score: int
    fit_reasoning: str
    gaps: list[str] = Field(default_factory=list, sa_column=Column(JSON))

    title_variant: str
    summary_text: str
    selected_bullet_ids: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    # The bullet text as it was printed, not a join against today's profile. The
    # profile keeps changing and this has to show what the employer actually read.
    selected_bullets: list[dict] = Field(default_factory=list, sa_column=Column(JSON))

    # The PDF itself, not a path. ~80 KB each, so a hundred applications is 8 MB,
    # and keeping it here means the whole app is one file to back up and no
    # deployment needs a writable disk.
    pdf: bytes = Field(sa_column=Column(LargeBinary))
    filename: str

    status: str = "generated"
    applied_at: datetime | None = None
    created_at: datetime = Field(default_factory=now)
    notes: str | None = None
