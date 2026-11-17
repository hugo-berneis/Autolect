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
    monkeypatch.setattr(settings, "compress_audio", False)  # opt-in per test
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


def _wire_providers(engine) -> None:
    from app.notes.fake import FakeNotesProvider
    from app.transcription.fake import FakeTranscriptionProvider

    app.state.transcriber.set_provider(FakeTranscriptionProvider())
    app.state.transcriber.session_factory = lambda: Session(engine)
    app.state.notes_engine.set_provider(FakeNotesProvider())
    app.state.notes_engine.session_factory = lambda: Session(engine)


@pytest.fixture
def client(engine) -> Iterator[TestClient]:
    from app.auth import get_current_user

    def override() -> Iterator[Session]:
        with Session(engine) as s:
            yield s

    app.dependency_overrides[get_session] = override
    app.dependency_overrides[get_current_user] = lambda: "default"  # bypass auth
    _wire_providers(engine)

    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def rawclient(engine, monkeypatch) -> Iterator[TestClient]:
    """Client with real auth enabled (no get_current_user override)."""
    from app.config import settings

    monkeypatch.setattr(settings, "app_password", "secret")

    def override() -> Iterator[Session]:
        with Session(engine) as s:
            yield s

    app.dependency_overrides[get_session] = override
    _wire_providers(engine)

    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
