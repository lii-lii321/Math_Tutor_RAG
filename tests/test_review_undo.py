"""评分撤销（快照/恢复）服务测试。"""
from __future__ import annotations

import uuid

import pytest

from backend.database import SessionLocal
from backend.models.orm import ReviewLog, User
from backend.services.question_service import QuestionService


@pytest.fixture
def undo_service():
    return QuestionService(session_factory=SessionLocal)


@pytest.fixture
def undo_user(db_session):
    user = User(username=f"undo_{uuid.uuid4().hex[:8]}", password_hash="x", role="student")
    db_session.add(user)
    db_session.commit()
    return user


class TestSnapshotRestore:
    def test_roundtrip_restores_sm2_state(self, undo_service, undo_user):
        """标准撤销流：评分前快照 → 评分 → 恢复 → SM-2 与日志回到评分前。"""
        q = undo_service.create_manual_question(undo_user.id, content_markdown="撤销题2")
        before = undo_service.snapshot_review_state(q.id, undo_user.id)
        assert before is not None and before["reps"] == 0
        assert before["last_log_id"] is None

        graded = undo_service.grade_review(q.id, undo_user.id, "good")
        assert graded is not None and graded.reps == 1

        restored = undo_service.restore_review_state(q.id, undo_user.id, before)
        assert restored is True
        after = undo_service.get_question(q.id, undo_user.id)
        assert after is not None
        assert after.reps == 0
        assert after.due_at is None  # 回到未排期状态

        with SessionLocal() as session:
            logs = (
                session.query(ReviewLog).filter_by(question_id=q.id).all()
            )
        assert logs == [], "撤销应删除该次评分写入的复习日志"

    def test_snapshot_includes_last_log_id(self, undo_service, undo_user):
        q = undo_service.create_manual_question(undo_user.id, content_markdown="快照题")
        undo_service.grade_review(q.id, undo_user.id, "easy")
        snapshot = undo_service.snapshot_review_state(q.id, undo_user.id)
        assert snapshot is not None
        assert snapshot["last_log_id"] is not None
        assert snapshot["reps"] == 1

    def test_restore_rejects_missing_or_foreign(self, undo_service, undo_user, db_session):
        stranger = User(username=f"undo_x_{uuid.uuid4().hex[:8]}", password_hash="x", role="student")
        db_session.add(stranger)
        db_session.commit()

        assert undo_service.snapshot_review_state(999_999, undo_user.id) is None

        saved = undo_service.create_manual_question(undo_user.id, content_markdown="别人的题")
        snapshot = undo_service.snapshot_review_state(saved.id, undo_user.id)
        assert snapshot is not None
        assert undo_service.restore_review_state(saved.id, stranger.id, snapshot) is False

    def test_undo_reverts_failed_grade(self, undo_service, undo_user):
        """again 评分的撤销同样还原（reps 回 0、队列外语义由 UI 保证）。"""
        q = undo_service.create_manual_question(undo_user.id, content_markdown="again 撤销题")
        before = undo_service.snapshot_review_state(q.id, undo_user.id)
        graded = undo_service.grade_review(q.id, undo_user.id, "again")
        assert graded is not None and graded.reps == 0 and graded.interval_days < 1

        assert undo_service.restore_review_state(q.id, undo_user.id, before) is True
        with SessionLocal() as session:
            logs = session.query(ReviewLog).filter_by(question_id=q.id).all()
        assert logs == []
