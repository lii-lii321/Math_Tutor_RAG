"""Alembic 迁移冒烟测试：baseline 能在空库上建出完整 schema。"""
from __future__ import annotations

import sqlite3
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_baseline_migration_creates_schema(tmp_path, monkeypatch):
    from alembic import command
    from alembic.config import Config

    db = tmp_path / "migration_test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db.as_posix()}")

    # 锚定仓库根：测试可在任意 cwd 下运行（与 pyproject 的 rootdir 语义一致）
    cfg = Config(str(PROJECT_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(PROJECT_ROOT / "migrations"))
    command.upgrade(cfg, "head")

    conn = sqlite3.connect(db)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"users", "questions", "review_logs", "alembic_version"} <= tables

    # 版本表已标记到 head
    (version,) = conn.execute("SELECT version_num FROM alembic_version").fetchone()
    assert version
