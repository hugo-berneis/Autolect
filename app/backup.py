"""One-command backup / restore of the whole library.

A backup is a single .tar.gz containing:
  - autolect.db           (the SQLite database — the source of truth)
  - audio/...             (all recordings, WAV or Opus)
  - notes/<id>_<slug>.md  (notes exported as Markdown for portability)

Restore replaces the database and audio from an archive (notes .md are derived
from the DB, so they are informational only on restore).

CLI:
  python -m app.backup create [archive.tar.gz]
  python -m app.backup restore <archive.tar.gz>
"""
from __future__ import annotations

import argparse
import io
import os
import shutil
import tarfile
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlmodel import Session, select

from .config import settings
from .db import engine as default_engine
from .models import Lecture


def _slug(title: str) -> str:
    keep = "".join(c if c.isalnum() or c in " -_" else "" for c in title).strip()
    return (keep.replace(" ", "_") or "lecture")[:80]


def create_backup(archive_path: str | None = None, eng=None) -> str:
    eng = eng or default_engine
    if archive_path is None:
        stamp = time.strftime("%Y%m%d-%H%M%S")
        archive_path = f"autolect-backup-{stamp}.tar.gz"
    db_path = Path(settings.db_path)
    audio_dir = Path(settings.audio_dir)

    with tarfile.open(archive_path, "w:gz") as tar:
        if db_path.exists():
            tar.add(str(db_path), arcname="autolect.db")
        if audio_dir.exists():
            for f in sorted(audio_dir.iterdir()):
                if f.is_file():
                    tar.add(str(f), arcname=f"audio/{f.name}")
        # notes as .md
        try:
            with Session(eng) as db:
                lectures = db.exec(select(Lecture)).all()
        except Exception:  # DB not initialized yet — back up files only
            lectures = []
        for lecture in lectures:
            if not lecture.notes_markdown.strip():
                continue
            data = lecture.notes_markdown.encode("utf-8")
            info = tarfile.TarInfo(f"notes/{lecture.id}_{_slug(lecture.title)}.md")
            info.size = len(data)
            info.mtime = int(time.time())
            tar.addfile(info, io.BytesIO(data))
    return archive_path


def restore_backup(archive_path: str) -> None:
    db_path = Path(settings.db_path)
    audio_dir = Path(settings.audio_dir)
    with tempfile.TemporaryDirectory() as tmp:
        with tarfile.open(archive_path, "r:gz") as tar:
            _safe_extract(tar, tmp)
        src_db = Path(tmp) / "autolect.db"
        if src_db.exists():
            db_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_db, db_path)
        src_audio = Path(tmp) / "audio"
        if src_audio.exists():
            if audio_dir.exists():
                shutil.rmtree(audio_dir)
            shutil.copytree(src_audio, audio_dir)
        else:
            audio_dir.mkdir(parents=True, exist_ok=True)


def _safe_extract(tar: tarfile.TarFile, dest: str) -> None:
    dest_path = Path(dest).resolve()
    for member in tar.getmembers():
        target = (dest_path / member.name).resolve()
        if not str(target).startswith(str(dest_path)):
            raise ValueError(f"unsafe path in archive: {member.name}")
    tar.extractall(dest)


def delete_old_audio(days: int, eng=None) -> int:
    """Delete audio files for lectures older than `days` (keep transcript+notes).
    Returns the number of files removed. No-op when days <= 0."""
    if days <= 0:
        return 0
    eng = eng or default_engine
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    removed = 0
    with Session(eng) as db:
        for lecture in db.exec(select(Lecture)).all():
            if (
                lecture.audio_path
                and lecture.created_at.replace(tzinfo=timezone.utc) < cutoff
                and os.path.exists(lecture.audio_path)
            ):
                os.remove(lecture.audio_path)
                lecture.audio_path = None
                lecture.audio_bytes = 0
                lecture.disk_bytes = 0
                db.add(lecture)
                removed += 1
        db.commit()
    return removed


def _main() -> None:
    parser = argparse.ArgumentParser(description="autolect library backup/restore")
    sub = parser.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("create", help="create a backup archive")
    c.add_argument("archive", nargs="?", default=None)
    r = sub.add_parser("restore", help="restore from a backup archive")
    r.add_argument("archive")
    args = parser.parse_args()
    if args.cmd == "create":
        path = create_backup(args.archive)
        print(f"Backup written to {path}")
    elif args.cmd == "restore":
        restore_backup(args.archive)
        print(f"Restored from {args.archive}")


if __name__ == "__main__":
    _main()
