"""种子账号开关测试（提升项 #18）：SEED_USERS=false 时空库不建固定凭据账号。"""
from __future__ import annotations

import sqlite3

import pytest

from backend.config import Settings


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    """把 backend.database 的 engine/SessionLocal 换成独立空库文件。"""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    import backend.database as db_mod

    db_file = str(tmp_path / "seed_flag.db")
    engine = create_engine("sqlite:///" + db_file.replace("\\", "/"), future=True)
    monkeypatch.setattr(db_mod, "engine", engine)
    monkeypatch.setattr(
        db_mod,
        "SessionLocal",
        sessionmaker(bind=engine, expire_on_commit=False, future=True),
    )
    yield db_file
    engine.dispose()


def _user_count(db_file: str) -> int:
    conn = sqlite3.connect(db_file)
    try:
        return conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    finally:
        conn.close()


def test_seed_users_false_creates_no_accounts(monkeypatch, isolated_db):
    """配置 SEED_USERS=false：建表但零账号（默认口令不再进空库）。"""
    import backend.database as db_mod
    from backend.database import init_db

    monkeypatch.setenv("SEED_USERS", "false")
    settings = Settings()
    assert settings.seed_users is False  # 环境变量已被拾取
    monkeypatch.setattr(db_mod, "_settings", settings)
    init_db()
    assert _user_count(isolated_db) == 0


def test_seed_users_default_true_seeds_two_accounts(isolated_db):
    """显式 seed_users=True（默认语义）：空库建 admin/demo 两个账号。"""
    from backend.database import init_db

    init_db(seed_users=True)
    assert _user_count(isolated_db) == 2
