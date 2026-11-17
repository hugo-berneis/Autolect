"""Backup/restore round-trip + download endpoint."""
from __future__ import annotations

import tarfile

from sqlmodel import Session, SQLModel, create_engine, select

from app import backup
from app.models import Lecture, LectureStatus


def test_backup_restore_roundtrip(tmp_path, monkeypatch):
    from app.config import settings

    dbfile = tmp_path / "lib.db"
    audio = tmp_path / "audio"
    audio.mkdir(exist_ok=True)  # autouse fixture may have created it
    monkeypatch.setattr(settings, "db_path", dbfile)
    monkeypatch.setattr(settings, "audio_dir", audio)

    eng = create_engine(f"sqlite:///{dbfile}")
    SQLModel.metadata.create_all(eng)
    with Session(eng) as s:
        s.add(
            Lecture(title="Lecture One", notes_markdown="# Notes\nhi", status=LectureStatus.ready)
        )
        s.commit()
    (audio / "lecture_1.opus").write_bytes(b"opus-bytes")

    archive = str(tmp_path / "bk.tar.gz")
    backup.create_backup(archive, eng=eng)

    with tarfile.open(archive) as t:
        names = t.getnames()
    assert "autolect.db" in names
    assert any(n.startswith("audio/") for n in names)
    assert any(n.startswith("notes/") and n.endswith(".md") for n in names)

    # wipe and restore
    dbfile.unlink()
    (audio / "lecture_1.opus").unlink()
    backup.restore_backup(archive)

    assert dbfile.exists()
    assert (audio / "lecture_1.opus").read_bytes() == b"opus-bytes"
    eng2 = create_engine(f"sqlite:///{dbfile}")
    with Session(eng2) as s:
        rows = s.exec(select(Lecture)).all()
        assert len(rows) == 1 and rows[0].title == "Lecture One"


def test_backup_endpoint_returns_gzip(client):
    r = client.get("/api/backup")
    assert r.status_code == 200
    assert r.content[:2] == b"\x1f\x8b"  # gzip magic number
