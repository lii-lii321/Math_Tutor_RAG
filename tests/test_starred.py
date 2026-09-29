"""错题星标收藏测试。"""
from __future__ import annotations

import uuid

import pytest

from backend.database import SessionLocal, init_db
from backend.models.orm import User
from backend.services.question_service import QuestionService


@pytest.fixture
def service():
    return QuestionService(session_factory=SessionLocal)


@pytest.fixture
def star_user(db_session):
    user = User(username=f"star_{uuid.uuid4().hex[:8]}", password_hash="x", role="student")
    db_session.add(user)
    db_session.commit()
    return user


class TestToggleStar:
    def test_toggle_roundtrip(self, service, star_user):
        saved = service.create_manual_question(star_user.id, content_markdown="星标题")
        assert saved.starred is False

        assert service.toggle_star(saved.id, star_user.id) is True
        updated = service.get_question(saved.id, star_user.id)
        assert updated is not None and updated.starred is True

        assert service.toggle_star(saved.id, star_user.id) is False
        updated = service.get_question(saved.id, star_user.id)
        assert updated is not None and updated.starred is False

    def test_toggle_rejects_missing(self, service, star_user):
        assert service.toggle_star(999_999, star_user.id) is None

    def test_toggle_isolated_per_user(self, service, star_user, db_session):
        owner = User(username=f"star_o_{uuid.uuid4().hex[:8]}", password_hash="x", role="student")
        db_session.add(owner)
        db_session.commit()
        saved = service.create_manual_question(owner.id, content_markdown="别人的题")

        assert service.toggle_star(saved.id, star_user.id) is None
        updated = service.get_question(saved.id, owner.id)
        assert updated is not None and updated.starred is False


class TestStarredFilter:
    def test_list_filter_starred(self, service, star_user):
        a = service.create_manual_question(star_user.id, content_markdown="普通题A")
        b = service.create_manual_question(star_user.id, content_markdown="星标题B")
        service.toggle_star(b.id, star_user.id)

        starred_only = service.list_questions(star_user.id, starred=True, semantic=False)
        assert [q.id for q in starred_only] == [b.id]

        all_rows = service.list_questions(star_user.id, semantic=False)
        assert {q.id for q in all_rows} == {a.id, b.id}

        count = service.count_for_user(star_user.id, starred=True)
        assert count == 1

    def test_filter_via_keyword_semantic_path(self, service, star_user):
        """语义检索管线末端同样应用星标过滤。"""
        plain = service.create_manual_question(star_user.id, content_markdown="判别式普通题")
        hit = service.create_manual_question(star_user.id, content_markdown="判别式星标题")
        service.toggle_star(hit.id, star_user.id)

        rows = service.list_questions(
            star_user.id, keyword="判别式", starred=True, semantic=True
        )
        assert [q.id for q in rows] == [hit.id]
        assert plain.id not in {q.id for q in rows}

    def test_star_survives_tag_edits(self, service, star_user):
        """星标状态与标签编辑互不影响。"""
        saved = service.create_manual_question(star_user.id, content_markdown="星标与标签", tags=["旧"])
        service.toggle_star(saved.id, star_user.id)
        service.update_question(saved.id, star_user.id, tags=["新"])

        updated = service.get_question(saved.id, star_user.id)
        assert updated is not None
        assert updated.starred is True
        assert updated.tags == ["新"]


def test_migration_defaults_unstarred(service, star_user):
    """迁移后存量/新建题默认未星标（默认值验证）。"""
    init_db(seed_users=True)
    saved = service.create_manual_question(star_user.id, content_markdown="默认未星标")
    with SessionLocal() as session:
        from backend.models.orm import Question

        raw = session.get(Question, saved.id)
        assert raw.starred is False
