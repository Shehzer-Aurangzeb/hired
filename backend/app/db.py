"""Database engine, request session dependency, and SQLite pragmas."""

from collections.abc import Generator
from typing import Annotated, Any

from fastapi import Depends
from sqlalchemy import event
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from .settings import get_settings
from . import tables  # noqa: F401  -- imported so create_all sees the tables

settings = get_settings()
sqlite = settings.database_url.startswith("sqlite")

# An in-memory database belongs to its connection, so a pool would hand each
# request a different, empty one. StaticPool keeps everyone on the same one.
memory = settings.database_url in ("sqlite://", "sqlite:///:memory:")

engine = create_engine(
    settings.database_url,
    # SQLite ties a connection to its thread; FastAPI runs sync routes on a
    # threadpool. Postgres needs neither argument.
    connect_args={"check_same_thread": False} if sqlite else {},
    **({"poolclass": StaticPool} if memory else {}),
)


if sqlite:

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(connection: Any, _record: Any) -> None:
        # WAL lets reads and writes overlap instead of "database is locked".
        connection.execute("PRAGMA journal_mode=WAL")
        # SQLite ignores CHECK and FOREIGN KEY constraints unless asked.
        connection.execute("PRAGMA foreign_keys=ON")


def init_db() -> None:
    """create_all, no migrations: a schema change is a hand ALTER TABLE."""
    SQLModel.metadata.create_all(engine)


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]
