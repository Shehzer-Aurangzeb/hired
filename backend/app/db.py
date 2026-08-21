from collections.abc import Generator
from typing import Annotated, Any

from fastapi import Depends
from sqlalchemy import event
from sqlmodel import Session, SQLModel, create_engine

from .settings import get_settings
from . import tables  # noqa: F401  -- imported so create_all sees the tables

settings = get_settings()
sqlite = settings.database_url.startswith("sqlite")

engine = create_engine(
    settings.database_url,
    # SQLite ties a connection to the thread that opened it, and FastAPI runs
    # sync endpoints on a threadpool. Postgres needs neither argument.
    connect_args={"check_same_thread": False} if sqlite else {},
)


if sqlite:

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(connection: Any, _record: Any) -> None:
        # WAL lets a read and a write overlap instead of raising "database is
        # locked", which is otherwise reachable with a single user and two tabs.
        connection.execute("PRAGMA journal_mode=WAL")
        # SQLite ignores CHECK and FOREIGN KEY constraints unless asked.
        connection.execute("PRAGMA foreign_keys=ON")


def init_db() -> None:
    """
    ponytail: create_all, no Alembic. Two tables and one user, so a schema change
    is an ALTER TABLE by hand. Add migrations the first time that is not true.
    """
    SQLModel.metadata.create_all(engine)


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]
