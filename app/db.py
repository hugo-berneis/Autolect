"""Database engine and session dependency."""
from __future__ import annotations

from collections.abc import Iterator

from sqlmodel import Session, create_engine

from .config import settings

# check_same_thread=False: FastAPI may use the connection across threads.
engine = create_engine(
    settings.database_url,
    echo=False,
    connect_args={"check_same_thread": False},
)


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
