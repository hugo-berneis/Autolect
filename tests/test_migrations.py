"""Verify the Alembic migration builds the full schema from scratch."""
from __future__ import annotations

import sqlite3

from alembic import command
from alembic.config import Config


def test_migration_creates_all_tables(tmp_path, monkeypatch):
    from app.config import settings

    db = tmp_path / "migrated.db"
    monkeypatch.setattr(settings, "db_path", db)

    command.upgrade(Config("alembic.ini"), "head")

    con = sqlite3.connect(db)
    names = {r[0] for r in con.execute("select name from sqlite_master where type='table'")}
    con.close()
    assert {"course", "template", "lecture", "transcriptsegment"} <= names
