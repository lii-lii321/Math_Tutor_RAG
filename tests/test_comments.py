"""批注服务与 API 测试。"""
from __future__ import annotations

import pytest

from backend.services.comment_service import CommentService
from backend.services.question_service import QuestionService


@pytest.fixture
def comment_service():
    return CommentService()


@pytest.fixture
def question_id(service, student_user):
    saved, _ = service.analyze_and_save(
        student_user.id, b"\xff\xd8\xff" + b"1" * 16, user_tags=["批注测试"]
    )
    return saved.id


@pytest.fixture
def service():
    from backend.database import SessionLocal

    return QuestionService(session_factory=SessionLocal)


def test_add_and_list_comments(comment_service, question_id, student_user):
    comment_service.add(question_id, student_user.id, "老师说得对，这里要分类讨论")
    comments = comment_service.list_for_question(question_id)
    assert len(comments) == 1
    assert comments[0]["author"] == "demo"
    assert "分类讨论" in comments[0]["content"]


def test_add_empty_comment_rejected(comment_service, question_id, student_user):
    with pytest.raises(ValueError):
        comment_service.add(question_id, student_user.id, "   ")


def test_add_comment_to_missing_question(comment_service, student_user):
    with pytest.raises(ValueError):
        comment_service.add(999999, student_user.id, "内容")


def test_delete_permissions(comment_service, db_session, question_id, student_user):
    from backend.models.orm import User
    from backend.utils.security import hash_password

    added = comment_service.add(question_id, student_user.id, "作者批注")

    author_deleted = comment_service.delete(added["id"], student_user.id)
    assert author_deleted is True

    added2 = comment_service.add(question_id, student_user.id, "再来一条")
    stranger = User(username="comment_stranger", password_hash=hash_password("x", 4), role="student")
    db_session.add(stranger)
    db_session.commit()
    assert comment_service.delete(added2["id"], stranger.id) is False  # 陌生人不能删
    teacher = User(username="comment_teacher", password_hash=hash_password("x", 4), role="teacher")
    db_session.add(teacher)
    db_session.commit()
    assert comment_service.delete(added2["id"], teacher.id, is_teacher=True) is True


def test_latest_for_questions(comment_service, question_id, student_user):
    comment_service.add(question_id, student_user.id, "第一条")
    comment_service.add(question_id, student_user.id, "第二条（最新）")
    latest = comment_service.latest_for_questions([question_id])
    assert "第二条" in latest[question_id]["content"]
    assert comment_service.latest_for_questions([]) == {}
