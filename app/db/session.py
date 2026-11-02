"""Engine and session helpers."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Base


def sqlite_file(url: str) -> Path | None:
    """Return the file behind a sqlite URL, or None for memory databases."""
    if not url.startswith("sqlite"):
        return None
    if ":memory:" in url:
        return None
    raw = url.split("sqlite:///", 1)[-1]
    if not raw:
        return None
    return Path(raw)


def make_engine(url: str) -> Engine:
    """Create an engine. SQLite connections may be used from the watcher thread."""
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    engine = create_engine(url, connect_args=connect_args)
    if engine.dialect.name == "sqlite":

        @event.listens_for(engine, "connect")
        def _enable_foreign_keys(dbapi_connection: Any, _record: Any) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


def make_session_factory(url: str) -> tuple[sessionmaker[Session], Engine]:
    """Create the sqlite parent directory, the tables, and a session factory."""
    path = sqlite_file(url)
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
    engine = make_engine(url)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    return factory, engine


@contextmanager
def session_scope(factory: sessionmaker[Session]) -> Iterator[Session]:
    """Commit on success and roll back on any exception."""
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
