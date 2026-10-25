from __future__ import annotations

import io
import json
from pathlib import Path

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
        "判别式" in q.content_markdown
        or "判别式" in (q.answer or "")
        or any("判别式" in t for t in q.tags)
        or any("判别式" in t for t in q.knowledge_points)
        for q in by_keyword
    )


def test_knowledge_point_filter(question_service, student_user):
    """knowledge_point 过滤按规范化知识点字段命中，而非标签（提升项 #3 回归）。

    generate_practice_set 传知识点名（画像字段），修复前错按 tag 过滤返回空集。
    """
    service = question_service
    service.create_manual_question(
        student_user.id,
        content_markdown="求 y=2x²-8x+1 的最小值",
        answer="x=2 时取最小值 -7",
        knowledge_points=["二次函数的图象与性质"],
        tags=["函数"],
    )
    service.create_manual_question(
        student_user.id,
        content_markdown="解方程 x+3=7",
        answer="x=4",
        knowledge_points=["一元一次方程"],
        tags=["方程"],
    )

    hits = service.list_questions(
        student_user.id, knowledge_point="二次函数的图象与性质", semantic=False
    )
    assert len(hits) == 1
    assert "最小值" in hits[0].content_markdown

    # Agent 工具入口同口径：generate_practice_set(knowledge_point=...) 能取到题
    from backend.services.agent_tools import build_tools

    tools = {t.name: t for t in build_tools(service, student_user.id)}
    payload = json.loads(
        tools["generate_practice_set"].handler(size=5, knowledge_point="二次函数的图象与性质")
    )
    assert payload["count"] == 1
    assert payload["basis"].startswith("知识点专项")


def test_manual_question_with_answer_gets_verified(question_service, student_user):
    """手动录题带答案时跑数学验证（提升项 #4 回归）：错答案标 failed，空答案不验证。"""
    service = question_service

    wrong = service.create_manual_question(
        student_user.id,
        content_markdown="解方程 $x^2=4$",
        answer="$x=\\pm 3$",
    )
    assert wrong.verification_status == "failed"

    right = service.create_manual_question(
        student_user.id,
        content_markdown="解方程 $x^2=4$",
        answer="$x=\\pm 2$",
    )
    assert right.verification_status == "verified"

    no_answer = service.create_manual_question(
        student_user.id,
        content_markdown="整理：三角形内角和定理的证明思路",
    )
    assert no_answer.verification_status is None


def test_keyword_search_escapes_like_wildcards(question_service, student_user):
    """关键词含 LIKE 通配符时按字面匹配（审计 D3 回归）。

    修复前 f"%{keyword}%" 未转义：搜「0%」等价于「0」+任意串，命中膨胀。
    """
    service = question_service
    service.create_manual_question(
        student_user.id, content_markdown="甲商场打 100% 全场折扣题", answer="字面百分号"
    )
    service.create_manual_question(
        student_user.id, content_markdown="乙题蛇形变量名 snake_case_case 题", answer=""
    )
    # 干扰项：未转义时会被「e_ca」（_ 通配任意字符）误命中
    service.create_manual_question(
        student_user.id, content_markdown="丙题 eXca 通配干扰项", answer=""
    )

    # 字面「100%」能命中
    literal = service.list_questions(student_user.id, keyword="100%", semantic=False)
    assert any("100%" in q.content_markdown for q in literal)
    # 「10%」是字面三字符，甲题文本「100%」不含它，不得被通配符放行
    narrowed = service.list_questions(student_user.id, keyword="10%", semantic=False)
    assert not any("甲商场" in q.content_markdown for q in narrowed)
    # 下划线通配符字面化：「e_ca」只匹配字面 e_ca（乙题），不匹配 eXca（丙题）
    underscore = service.list_questions(student_user.id, keyword="e_ca", semantic=False)
    assert any("snake_case_case" in q.content_markdown for q in underscore)
    assert not any("eXca" in q.content_markdown for q in underscore)


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


def test_persist_image_compresses_large_images(question_service, student_user):
    from PIL import Image

    from backend.utils.paths import resolve_image_path

    big = Image.new("RGB", (2400, 1200), (10, 60, 130))
    stream = io.BytesIO()
    big.save(stream, format="JPEG", quality=95)
    raw_size = len(stream.getvalue())

    saved, _ = question_service.analyze_and_save(student_user.id, stream.getvalue())
    # image_path 现在存 data_dir 相对路径（换机可移植），读取时解析回绝对路径
    assert not Path(saved.image_path).is_absolute()
    image_abs = resolve_image_path(saved.image_path)
    with Image.open(image_abs) as stored:
        assert max(stored.size) <= 1600
    assert image_abs.stat().st_size < raw_size


def test_analyze_and_save_dedup_returns_existing(question_service, student_user, db_session):
    jpeg = _tiny_jpeg()
    first_result = question_service.analyze_and_save_dedup(student_user.id, jpeg)
    assert first_result.duplicated is False

    second_result = question_service.analyze_and_save_dedup(student_user.id, jpeg)
    assert second_result.duplicated is True
    assert second_result.question.id == first_result.question.id  # 复用既有记录

    all_questions = question_service.list_questions(student_user.id, semantic=False)
    assert len([q for q in all_questions if q.id == first_result.question.id]) == 1

    # 其他用户上传同图是独立错题（按用户隔离）
    from backend.models.orm import User

    other = User(username="dedup_other", password_hash="x", role="student")
    db_session.add(other)
    db_session.commit()
    other_result = question_service.analyze_and_save_dedup(other.id, jpeg)
    assert other_result.duplicated is False
    assert other_result.question.id != first_result.question.id


def test_update_and_delete(question_service, student_user):
    saved, _ = question_service.analyze_and_save(student_user.id, _tiny_jpeg())
    updated = question_service.update_question(
        saved.id, student_user.id, answer="修正后的答案", tags=["更新标签"]
    )
    assert updated is not None and updated.answer == "修正后的答案"

    noted = question_service.update_question(
        saved.id, student_user.id, user_note="自己的易错备注"
    )
    assert noted is not None and noted.user_note == "自己的易错备注"

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
    assert {
        "total", "reviewed", "due", "streak",
        "calendar", "accuracy_trend", "tag_stats", "weak_tags", "activity",
    } <= set(stats)
    assert stats["total"] >= 1
    assert stats["streak"] >= 1  # 今天录入了错题，连击至少 1 天
    assert stats["calendar"]["max"] >= 1
    assert len(stats["activity"]) == 14


def test_sanitize_tags_variants():
    assert sanitize_tags("a, b，c； d") == ["a", "b", "c", "d"]
    assert sanitize_tags("") == []
    assert sanitize_tags("重复,重复") == ["重复"]


def test_service_accepts_session_factory_singleton():
    service = QuestionService(session_factory=SessionLocal)
    assert service.vector_store is not None
    assert service.ai is not None
