"""pytest 全局夹具。

在导入任何 backend 模块之前设置测试环境变量，
确保 Settings / engine 单例在测试配置下构建。
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="mathmaster_test_"))
os.environ["DATABASE_URL"] = f"sqlite:///{(_TMP / 'test.db').as_posix()}"
os.environ["DATA_DIR"] = str(_TMP / "data")
os.environ["CHROMA_DIR"] = str(_TMP / "chroma")
os.environ["RAG_ENABLED"] = "true"  # 允许向量库参与集成测试
os.environ["AI_PROVIDER"] = "mock"
os.environ["BCRYPT_ROUNDS"] = "4"  # 加速测试

import pytest  # noqa: E402

from backend.database import SessionLocal, init_db  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _database() -> None:
    init_db(seed_users=True)


@pytest.fixture
def db_session():
    session = SessionLocal()
    try:
        yield session
        session.rollback()
    finally:
        session.close()


@pytest.fixture
def student_user(db_session):
    from backend.models.orm import User

    user = db_session.query(User).filter_by(username="demo").one()
    return user


@pytest.fixture
def question_service():
    from backend.services.question_service import QuestionService

    return QuestionService(session_factory=SessionLocal)
