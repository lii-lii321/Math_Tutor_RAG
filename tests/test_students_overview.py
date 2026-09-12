"""教师学生总览测试。"""
from __future__ import annotations

import io

import pytest
from PIL import Image

from backend.database import SessionLocal
from backend.services.question_service import QuestionService


def _tiny_jpeg() -> bytes:
    image = Image.new("RGB", (8, 8), (150, 150, 220))
    stream = io.BytesIO()
    image.save(stream, format="JPEG")
    return stream.getvalue()


@pytest.fixture
def service():
    return QuestionService(session_factory=SessionLocal)


def _make_user(db_session, username: str, role: str):
    from backend.models.orm import User
    from backend.utils.security import hash_password

    user = User(username=username, password_hash=hash_password("x", rounds=4), role=role)
    db_session.add(user)
    db_session.commit()
    return user


def test_students_overview_requires_teacher(service, db_session, student_user):
    teacher = _make_user(db_session, "report_teacher", "teacher")
    fresh = _make_user(db_session, "overview_student1", "student")
    service.analyze_and_save(fresh.id, _tiny_jpeg(), user_tags=["几何"])

    rows = service.students_overview(teacher.id)
    target = [r for r in rows if r["user_id"] == fresh.id]
    assert target, "教师应能看到学生"
    row = target[0]
    assert row["total"] >= 1
    assert row["due"] >= 1  # 新错题待复习
    assert row["reviewed"] == 0

    with pytest.raises(PermissionError):
        service.students_overview(student_user.id)  # 学生无权查看


def test_students_overview_counts_reviews(service, db_session):
    teacher = _make_user(db_session, "report_teacher2", "teacher")
    fresh = _make_user(db_session, "overview_student2", "student")
    saved, _ = service.analyze_and_save(fresh.id, _tiny_jpeg())
    service.grade_review(saved.id, fresh.id, "good")

    rows = service.students_overview(teacher.id)
    row = next(r for r in rows if r["user_id"] == fresh.id)
    assert row["total"] == 1
    assert row["reviewed"] == 1
    assert row["due"] == 0  # 唯一一道题刚复习过，good 调度 1 天后到期
