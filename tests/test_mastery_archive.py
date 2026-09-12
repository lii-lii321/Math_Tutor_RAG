"""掌握归档与复习历史测试。"""
from __future__ import annotations

import io

import pytest
from PIL import Image

from backend.database import SessionLocal
from backend.models.schemas import QuestionOut
from backend.services.question_service import QuestionService


def _tiny_jpeg() -> bytes:
    image = Image.new("RGB", (8, 8), (90, 200, 150))
    stream = io.BytesIO()
    image.save(stream, format="JPEG")
    return stream.getvalue()


@pytest.fixture
def service():
    return QuestionService(session_factory=SessionLocal)


def _question(reps: int, interval: float) -> QuestionOut:
    return QuestionOut(
        id=1, user_id=1, image_path=None, content_markdown="x", answer="y",
        reps=reps, interval_days=interval,
    )


def test_mastered_threshold():
    assert _question(3, 21).mastered is True
    assert _question(5, 60).mastered is True
    assert _question(2, 30).mastered is False  # 次数不足
    assert _question(3, 10).mastered is False  # 间隔不足
    assert _question(0, 0).mastered is False


def test_mastered_questions_leave_due_pool(service, db_session, student_user):
    fresh = None
    from backend.models.orm import User

    student = User(username="archive_student", password_hash="x", role="student")
    db_session.add(student)
    db_session.commit()

    saved, _ = service.analyze_and_save(student.id, _tiny_jpeg())
    fresh = saved.id

    # 模拟已掌握状态：3 次复习、21 天间隔
    from backend.database import get_session

    with get_session() as session:
        from backend.models.orm import Question

        question = session.get(Question, fresh)
        question.reps = 3
        question.interval_days = 21
        question.due_at = question.created_at  # 已到期

    due = service.due_questions(student.id)
    assert all(q.id != fresh for q in due), "已掌握的题不应再进入复习池"


def test_recent_reviews_shape(service, db_session):
    student = None
    from backend.models.orm import User

    student = User(username="history_student", password_hash="x", role="student")
    db_session.add(student)
    db_session.commit()

    saved, _ = service.analyze_and_save(student.id, _tiny_jpeg())
    service.grade_review(saved.id, student.id, "good")

    rows = service.recent_reviews(student.id, limit=20)
    assert len(rows) == 1
    row = rows[0]
    assert row["grade"] == "good"
    assert row["snippet"]
    assert row["reviewed_at"] is not None
