"""数据体检与修复测试：索引漂移检测、修复闭环、孤儿图片清理。"""
from __future__ import annotations

import uuid

import pytest

from backend.config import get_settings
from backend.database import SessionLocal, init_db
from backend.models.orm import User
from backend.services.data_health import DataHealthService
from backend.services.rag import QuestionVectorStore


@pytest.fixture
def health_user() -> User:
    init_db(seed_users=True)
    with SessionLocal() as session:
        user = User(username=f"hp_{uuid.uuid4().hex[:10]}", password_hash="x", role="student")
        session.add(user)
        session.commit()
        session.refresh(user)
        return user


@pytest.fixture
def health_service() -> DataHealthService:
    return DataHealthService(session_factory=SessionLocal)


class TestDataHealth:
    def test_healthy_after_entry(self, health_service, health_user):
        """正常录入后体检应全部健康。"""
        from backend.services.question_service import QuestionService

        QuestionService(session_factory=SessionLocal).create_manual_question(
            health_user.id, content_markdown="体检健康题", knowledge_points=["体检点"], tags=["体检"]
        )
        report = health_service.check(health_user.id)
        assert report["question_count"] == 1
        assert report["vector_available"] is True
        assert report["missing_index"] == 0
        assert report["stale_index"] == 0
        assert report["issues"] == 0

    def test_detects_and_repairs_missing_index(self, health_service, health_user):
        """手动抽掉向量条目后体检应报缺失，修复后归零。"""
        from backend.services.question_service import QuestionService

        service = QuestionService(session_factory=SessionLocal)
        saved = service.create_manual_question(health_user.id, content_markdown="索引缺失题")

        QuestionVectorStore().delete_questions([saved.id])
        report = health_service.check(health_user.id)
        assert report["missing_index"] == 1
        assert saved.id in report["missing_index_ids"]
        assert report["issues"] >= 1

        result = health_service.repair_index(health_user.id)
        assert result["reindexed"] >= 1
        report_after = health_service.check(health_user.id)
        assert report_after["missing_index"] == 0

    def test_detects_and_repairs_stale_index(self, health_service, health_user):
        """向量库中不存在于数据库的残留条目应被体检发现并清理。"""
        store = QuestionVectorStore()
        ghost_id = 9_100_001
        store.upsert_question(ghost_id, "幽灵条目", user_id=health_user.id, tags=[])

        report = health_service.check(health_user.id)
        assert ghost_id in report["stale_index_ids"]

        result = health_service.repair_index(health_user.id)
        assert result["removed"] == 1
        report_after = health_service.check(health_user.id)
        assert ghost_id not in report_after["stale_index_ids"]

    def test_orphan_image_report_and_cleanup(self, health_service, health_user):
        """未被题目引用的图片应被报告，清理后消失。"""
        images_dir = get_settings().data_dir / "images" / f"u{health_user.id}"
        images_dir.mkdir(parents=True, exist_ok=True)
        orphan = images_dir / "orphan_test.jpg"
        orphan.write_bytes(b"\xff\xd8fake")
        referenced = images_dir / "referenced_test.jpg"
        referenced.write_bytes(b"\xff\xd8fake")

        from backend.services.question_service import QuestionService

        saved = QuestionService(session_factory=SessionLocal).create_manual_question(
            health_user.id, content_markdown="带图题"
        )
        with SessionLocal() as session:
            from backend.models.orm import Question

            question = session.get(Question, saved.id)
            question.image_path = str(referenced)
            session.commit()

        report = health_service.check(health_user.id)
        assert str(orphan) in report["orphan_images"]
        assert str(referenced) not in report["orphan_images"]

        removed = health_service.cleanup_orphan_images(health_user.id)
        assert removed >= 1
        assert not orphan.exists()
        assert referenced.exists()

    def test_isolated_per_user(self, health_service, health_user):
        """体检只看当前用户：他人的数据不影响报告。"""
        report = health_service.check(health_user.id)
        assert report["question_count"] == 0
        assert report["issues"] in {0, report["orphan_image_count"]}
