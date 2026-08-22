from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, Column, LargeBinary
from sqlmodel import JSON, Field, SQLModel

# Where you are with this employer. Whether a PDF exists is a separate fact
# (pdf is not None), so "generated" is not a stage: it conflated the two.
STATUSES = ("saved", "skipped", "applied", "replied", "interview", "rejected", "offer")

# Reaching any of these means the application went out, whatever route it took.
SENT = ("applied", "replied", "interview", "rejected", "offer")


def now() -> datetime:
    """
    Naive UTC. SQLite's DATETIME drops tzinfo on the way in, so storing an aware
    value only hides that. stamp() below puts the marker back on the way out.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


def stamp(value: datetime | None) -> str | None:
    """
    UTC-marked ISO, the only way a timestamp should leave this app. A naive one
    on the wire is read as local time by the browser, which shifts every
    relative date by the reader's offset.
    """
    return value.replace(tzinfo=timezone.utc).isoformat() if value else None


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
    One job posting you decided to keep.

    Not "one CV sent": the records worth the most are often the ones you did not
    apply to, kept for the gaps they exposed. So every CV-shaped column is
    nullable, and only the posting, the fit and the gaps are always there.
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

    # Null until a CV is generated for this posting, which may never happen.
    title_variant: str | None = None
    summary_text: str | None = None
    selected_bullet_ids: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    # The bullet text as it was printed, not a join against today's profile. The
    # profile keeps changing and this has to show what the employer actually read.
    selected_bullets: list[dict] = Field(default_factory=list, sa_column=Column(JSON))

    # The PDF itself, not a path. ~80 KB each, so a hundred applications is 8 MB,
    # and keeping it here means the whole app is one file to back up and no
    # deployment needs a writable disk. Null until export attaches one.
    pdf: bytes | None = Field(default=None, sa_column=Column(LargeBinary, nullable=True))
    filename: str | None = None

    status: str = "saved"
    applied_at: datetime | None = None
    created_at: datetime = Field(default_factory=now)
    notes: str | None = None
