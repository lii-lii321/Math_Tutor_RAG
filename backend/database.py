"""数据库引擎与会话管理。

SQLAlchemy 2.0 风格；默认 SQLite 零配置启动，通过 DATABASE_URL 可无缝切换 MySQL。
"""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from backend.config import get_settings
from backend.models.orm import Base
from backend.utils.logging import get_logger
from backend.utils.security import hash_password

logger = get_logger("database")


def _build_engine(url: str) -> Engine:
    kwargs: dict = {"pool_pre_ping": True, "future": True}
    if url.startswith("sqlite"):
        # busy timeout：多线程（Streamlit rerun / 并发请求）下等待写锁而非立刻报错
        kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30}
    return create_engine(url, **kwargs)


_settings = get_settings()
engine: Engine = _build_engine(_settings.database_url)

if engine.dialect.name == "sqlite":
    # WAL 模式：读写不互斥，显著降低「database is locked」概率
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True)


@contextmanager
def get_session() -> Iterator[Session]:
    """会话上下文：提交成功 / 异常回滚，确保连接归还。"""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db(seed_users: bool = True) -> None:
    """建表并写入种子账号（仅当用户表为空时）。"""
    _settings.ensure_dirs()
    Base.metadata.create_all(bind=engine)

    if not seed_users:
        return

    from backend.models.orm import User

    with get_session() as session:
        count = session.query(User).count()
        if count > 0:
            return
        session.add(
            User(
                username=_settings.seed_admin_username,
                password_hash=hash_password(
                    _settings.seed_admin_password, _settings.bcrypt_rounds
                ),
                role="teacher",
            )
        )
        session.add(
            User(
                username=_settings.seed_demo_username,
                password_hash=hash_password(
                    _settings.seed_demo_password, _settings.bcrypt_rounds
                ),
                role="student",
            )
        )
    logger.info(
        "数据库初始化完成，种子账号: %s / %s",
        _settings.seed_admin_username,
        _settings.seed_demo_username,
    )


def check_connection() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as exc:  # pragma: no cover - 仅在环境异常时触发
        logger.error("数据库连接失败: %s", exc)
        return False
