"""批量标签与笔记测试。"""
from __future__ import annotations

import pytest

from backend.database import SessionLocal
from backend.services.question_service import QuestionService


@pytest.fixture
def service():
    return QuestionService(session_factory=SessionLocal)


def test_add_tags_to_many_merges(service, db_session):
    from backend.models.orm import User

    s1 = User(username="batch_s1", password_hash="x", role="student")
    db_session.add(s1)
    db_session.commit()

    first = service.create_manual_question(s1.id, content_markdown="批量一", tags=["a"])
    second = service.create_manual_question(s1.id, content_markdown="批量二", tags=["b"])

    changed = service.add_tags_to_many(
        [first.id, second.id], s1.id, ["批量", "a"]
    )
    assert changed == 2

    updated_first = service.get_question(first.id, s1.id)
    assert updated_first is not None
    assert "批量" in updated_first.tags
    assert "a" in updated_first.tags  # 已有标签不会被重复添加


def test_add_tags_rejects_others_question(service, db_session, student_user):
    from backend.models.orm import User

    saved, _ = service.analyze_and_save(student_user.id, b"\xff\xd8\xff" + b"0" * 16)

    other = User(username="batch_other", password_hash="x", role="student")
    db_session.add(other)
    db_session.commit()

    assert service.add_tags_to_many([saved.id], other.id, ["x"]) == 0
