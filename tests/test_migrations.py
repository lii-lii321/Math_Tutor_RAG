"""Alembic 迁移冒烟测试：baseline 能在空库上建出完整 schema。"""
from __future__ import annotations

import sqlite3


def test_baseline_migration_creates_schema(tmp_path, monkeypatch):
    from alembic import command
    from alembic.config import Config

    db = tmp_path / "migration_test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db.as_posix()}")

    cfg = Config("alembic.ini")
    cfg.set_main_option("script_location", "migrations")
    command.upgrade(cfg, "head")

    conn = sqlite3.connect(db)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"users", "questions", "review_logs", "alembic_version"} <= tables

    # 版本表已标记到 head
    (version,) = conn.execute("SELECT version_num FROM alembic_version").fetchone()
    assert version
