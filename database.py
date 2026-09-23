"""One SQLite engine; one short-lived session per request."""

import os
from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


def make_engine(url: str):
    engine = create_engine(url, connect_args={"check_same_thread": False, "timeout": 15})

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")

    return engine


engine = make_engine(os.getenv("DATABASE_URL", "sqlite:///./onboard.db"))
SessionLocal = sessionmaker(bind=engine)


def init_db() -> None:
    import models  # noqa: F401 — register all three tables before create_all

    Base.metadata.create_all(engine)


def get_session() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session
