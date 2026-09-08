from __future__ import annotations

import io

from PIL import Image

from backend.database import SessionLocal
from backend.services.question_service import QuestionService, sanitize_tags


def _tiny_jpeg() -> bytes:
    image = Image.new("RGB", (8, 8), color=(200, 210, 255))
    stream = io.BytesIO()
    image.save(stream, format="JPEG")
    return stream.getvalue()


def test_analyze_and_save_full_pipeline(question_service, student_user):
    saved, analysis = question_service.analyze_and_save(
        student_user.id, _tiny_jpeg(), user_tags=["期末复习"], hint=""
    )
    assert saved.id > 0
    assert saved.tags and "期末复习" in saved.tags
    assert analysis.answer
    assert saved.image_path  # 图片已落盘


def test_list_and_keyword_search(question_service, student_user):
    question_service.analyze_and_save(student_user.id, _tiny_jpeg(), user_tags=["几何"])
    results = question_service.list_questions(student_user.id)
    assert results, "应能列出错题"

    by_tag = question_service.list_questions(student_user.id, tag="几何")
    assert all("几何" in q.tags for q in by_tag)

    by_keyword = question_service.list_questions(student_user.id, keyword="判别式", semantic=False)
    assert all(
        "判别式" in q.content_markdown or any("判别式" in t for t in q.tags)
        for q in by_keyword
    )


def test_isolation_between_users(question_service, db_session, student_user):
    from backend.models.orm import User

    other = User(username="other_user", password_hash="x", role="student")
    db_session.add(other)
    db_session.commit()  # 先提交，另一个连接才能看到该用户（FK 校验）

    mine, _ = question_service.analyze_and_save(student_user.id, _tiny_jpeg())
    visible = question_service.list_questions(student_user.id)
    assert any(q.id == mine.id for q in visible)

    other_view = question_service.list_questions(other.id)
    assert all(q.id != mine.id for q in other_view)


def test_update_and_delete(question_service, student_user):
    saved, _ = question_service.analyze_and_save(student_user.id, _tiny_jpeg())
    updated = question_service.update_question(
        saved.id, student_user.id, answer="修正后的答案", tags=["更新标签"]
    )
    assert updated is not None and updated.answer == "修正后的答案"

    deleted = question_service.delete_questions([saved.id], student_user.id)
    assert deleted == 1
    assert question_service.get_question(saved.id, student_user.id) is None


def test_review_grading_flow(question_service, student_user):
    saved, _ = question_service.analyze_and_save(student_user.id, _tiny_jpeg())

    due_before = question_service.due_questions(student_user.id)
    assert any(q.id == saved.id for q in due_before)  # 新错题立即可复习

    graded = question_service.grade_review(saved.id, student_user.id, "good")
    assert graded is not None and graded.reps == 1

    again = question_service.grade_review(saved.id, student_user.id, "again")
    assert again is not None and again.reps == 0


def test_dashboard_stats_shape(question_service, student_user):
    stats = question_service.dashboard_stats(student_user.id)
    assert {"total", "reviewed", "due", "streak", "tag_stats", "weak_tags", "activity"} <= set(stats)
    assert stats["total"] >= 1
    assert stats["streak"] >= 1  # 今天录入了错题，连击至少 1 天
    assert len(stats["activity"]) == 14


def test_sanitize_tags_variants():
    assert sanitize_tags("a, b，c； d") == ["a", "b", "c", "d"]
    assert sanitize_tags("") == []
    assert sanitize_tags("重复,重复") == ["重复"]


def test_service_accepts_session_factory_singleton():
    service = QuestionService(session_factory=SessionLocal)
    assert service.vector_store is not None
    assert service.ai is not None
