"""标签管理（重命名/删除）测试。"""
from __future__ import annotations

import io

import pytest
from PIL import Image

from backend.database import SessionLocal
from backend.services.question_service import QuestionService


@pytest.fixture
def service():
    return QuestionService(session_factory=SessionLocal)


def _tiny_jpeg() -> bytes:
    image = Image.new("RGB", (8, 8), (200, 120, 130))
    stream = io.BytesIO()
    image.save(stream, format="JPEG")
    return stream.getvalue()


def test_tag_usage_counts(service, student_user):
    service.create_manual_question(
        student_user.id, content_markdown="题一", tags=["甲", "乙"]
    )
    service.create_manual_question(
        student_user.id, content_markdown="题二", tags=["甲"]
    )
    usage = service.tag_usage(student_user.id)
    assert usage["甲"] == 2
    assert usage["乙"] == 1


def test_rename_tag_updates_questions(service, student_user):
    saved, _ = service.analyze_and_save(student_user.id, _tiny_jpeg(), user_tags=["旧标签"])
    saved2, _ = service.analyze_and_save(student_user.id, _tiny_jpeg(), user_tags=["旧标签"])

    changed = service.rename_tag(student_user.id, "旧标签", "新标签")
    assert changed == 2

    updated = service.list_questions(student_user.id, tag="新标签", semantic=False)
    assert {q.id for q in updated} == {saved.id, saved2.id}
    assert not service.list_questions(student_user.id, tag="旧标签", semantic=False)


def test_rename_tag_validation(service, student_user):
    with pytest.raises(ValueError):
        service.rename_tag(student_user.id, "", "x")
    with pytest.raises(ValueError):
        service.rename_tag(student_user.id, "x", "  ")
    # 同名重命名是无害的空操作
    assert service.rename_tag(student_user.id, "a", "a") == 0


def test_delete_tag_removes_everywhere(service, student_user):
    saved, _ = service.analyze_and_save(student_user.id, _tiny_jpeg(), user_tags=["待删"])
    changed = service.delete_tag(student_user.id, "待删")
    assert changed == 1
    updated = service.get_question(saved.id, student_user.id)
    assert updated is not None and "待删" not in updated.tags
