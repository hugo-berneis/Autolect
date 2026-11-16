"""Test fixtures: an isolated temp SQLite DB per test, wired into the app via a
dependency override (no real DB, no network)."""
from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

from app.db import get_session
from app.main import app


@pytest.fixture(autouse=True)
def tmp_dirs(tmp_path, monkeypatch):
    """Keep all file writes (audio, db) inside the test's tmp dir."""
    from app.config import settings

    monkeypatch.setattr(settings, "data_dir", tmp_path)
    monkeypatch.setattr(settings, "audio_dir", tmp_path / "audio")
    (tmp_path / "audio").mkdir(parents=True, exist_ok=True)


@pytest.fixture
def engine(tmp_path):
    db = tmp_path / "test.db"
    eng = create_engine(
        f"sqlite:///{db}", connect_args={"check_same_thread": False}
    )
    SQLModel.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def session(engine) -> Iterator[Session]:
    with Session(engine) as s:
        yield s


@pytest.fixture
def client(engine) -> Iterator[TestClient]:
    def override() -> Iterator[Session]:
        with Session(engine) as s:
            yield s

    app.dependency_overrides[get_session] = override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
