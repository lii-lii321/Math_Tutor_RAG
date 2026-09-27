"""知识点掌握度引擎与自适应复习计划（Batch 04/05）单元 + 集成测试。

使用独立用户隔离，避免与其他测试文件共享 demo 用户产生的数据污染。
"""
from __future__ import annotations

import datetime as dt
import uuid

import pytest

from backend.database import SessionLocal, init_db
from backend.models.orm import KnowledgePoint, QuestionKnowledgePoint, ReviewLog, User
from backend.services.mastery import (
    SHAKY_THRESHOLD,
    UNREVIEWED_SCORE,
    MasteryEngine,
    mastery_status,
    question_mastery,
    sync_question_links,
)
from backend.services.question_service import QuestionService


@pytest.fixture
def kp_user() -> User:
    init_db(seed_users=True)
    username = f"kp_{uuid.uuid4().hex[:10]}"
    with SessionLocal() as session:
        user = User(username=username, password_hash="x", role="student")
        session.add(user)
        session.commit()
        session.refresh(user)
        return user


@pytest.fixture
def service() -> QuestionService:
    return QuestionService(session_factory=SessionLocal)


@pytest.fixture
def engine() -> MasteryEngine:
    return MasteryEngine(SessionLocal)


def _make_question(service: QuestionService, user_id: int, points: list[str], **kw):
    return service.create_manual_question(
        user_id,
        content_markdown=kw.pop("content", "题面内容"),
        knowledge_points=points,
        **kw,
    )


def _add_review(question_id: int, user_id: int, grade: str, days_ago: float) -> None:
    with SessionLocal() as session:
        session.add(
            ReviewLog(
                question_id=question_id,
                user_id=user_id,
                grade=grade,
                quality=4,
                reviewed_at=dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days_ago),
            )
        )
        session.commit()


def _linked_names(question_id: int) -> list[str]:
    with SessionLocal() as session:
        links = (
            session.query(QuestionKnowledgePoint)
            .filter_by(question_id=question_id)
            .all()
        )
        return [session.get(KnowledgePoint, link.knowledge_point_id).name for link in links]


class TestSyncLinks:
    def test_entry_creates_kp_and_links(self, service, kp_user):
        q = _make_question(service, kp_user.id, ["洛必达法则", "洛必达法则"])
        assert _linked_names(q.id) == ["洛必达法则"]

    def test_sync_replaces_links(self, service, kp_user):
        q = _make_question(service, kp_user.id, ["数列极限"])
        with SessionLocal() as session:
            sync_question_links(session, q.id, ["函数极限"])
            session.commit()
        assert _linked_names(q.id) == ["函数极限"]

    def test_update_path_syncs(self, service, kp_user):
        q = _make_question(service, kp_user.id, [])
        updated = service.update_question(
            q.id, kp_user.id, knowledge_points=["级数收敛"]
        )
        assert updated is not None
        assert updated.knowledge_points == ["级数收敛"]
        assert _linked_names(q.id) == ["级数收敛"]

    def test_get_or_create_shared_kp(self, service, kp_user):
        a = _make_question(service, kp_user.id, ["二项分布"])
        b = _make_question(service, kp_user.id, ["二项分布"])
        with SessionLocal() as session:
            kps = session.query(KnowledgePoint).filter_by(name="二项分布").all()
        assert len(kps) == 1
        assert _linked_names(a.id) == _linked_names(b.id) == ["二项分布"]


class TestMasteryMath:
    def test_unreviewed_score(self):
        assert question_mastery([]) == UNREVIEWED_SCORE

    def test_recent_log_dominates(self):
        """权重随复习次序指数衰减：最近一次评分主导掌握度。"""
        recovered = [_log("again", 30), _log("good", 1)]
        lapsed = [_log("good", 30), _log("again", 1)]
        assert question_mastery(recovered) > question_mastery(lapsed)

    def test_recent_again_drops_mastery(self):
        steady = [_log("good", 30), _log("good", 20), _log("good", 10)]
        lapsed = [_log("good", 30), _log("good", 20), _log("again", 1)]
        assert question_mastery(lapsed) < question_mastery(steady)

    def test_status_bands(self):
        assert mastery_status(0.1) == "weak"
        assert mastery_status(0.5) == "shaky"
        assert mastery_status(0.9) == "solid"
        assert mastery_status(SHAKY_THRESHOLD) == "solid"


def _log(grade: str, days_ago: float) -> ReviewLog:
    return ReviewLog(
        question_id=1,
        user_id=1,
        grade=grade,
        quality=4,
        reviewed_at=dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days_ago),
    )


class TestProfile:
    def test_profile_orders_weak_first(self, service, kp_user, engine):
        strong = _make_question(service, kp_user.id, ["立体几何"])
        weak = _make_question(service, kp_user.id, ["排列组合"])
        _add_review(strong.id, kp_user.id, "good", 10)
        _add_review(strong.id, kp_user.id, "easy", 1)
        _add_review(weak.id, kp_user.id, "again", 1)

        profile = engine.profile(kp_user.id)
        by_name = {item.knowledge_point: item for item in profile}
        weak_item = by_name["排列组合"]
        strong_item = by_name["立体几何"]
        assert weak_item.status == "weak"
        assert weak_item.mastery == 0.0
        assert strong_item.status == "solid"
        assert weak_item.mastery < strong_item.mastery
        assert weak_item.question_count == 1
        names = [item.knowledge_point for item in profile]
        assert names.index("排列组合") < names.index("立体几何")

    def test_profile_empty_user(self, engine):
        assert engine.profile(4_242_424) == []


class TestTodayPlan:
    def test_plan_empty(self, engine):
        assert engine.today_plan(9_999_999) == []

    def test_plan_lists_questions_with_reasons(self, service, kp_user, engine):
        _make_question(service, kp_user.id, ["平面向量"])
        _make_question(service, kp_user.id, ["复数运算"])

        plan = engine.today_plan(kp_user.id, size=5)
        assert plan, "未复习的题应进入计划（到期池）"
        ids = [item.question.id for item in plan]
        assert len(ids) == len(set(ids)), "计划中题目不应重复"
        assert all(item.reason for item in plan)
        assert all(item.question.mastered is False for item in plan)

    def test_weak_kp_reinforcement_reason(self, service, kp_user, engine):
        weak_q = _make_question(service, kp_user.id, ["三角恒等变换"])
        # 评分 hard：题目被排期到未来（退出到期池），但 KP 掌握度只有 0.6（不稳固）
        updated = service.grade_review(weak_q.id, kp_user.id, "hard")
        assert updated is not None and not updated.mastered

        plan = engine.today_plan(kp_user.id, size=5)
        assert any("薄弱知识点" in item.reason for item in plan)

    def test_size_zero_and_cap(self, service, kp_user, engine):
        _make_question(service, kp_user.id, ["概率基础"])
        assert engine.today_plan(kp_user.id, size=0) == []
        assert len(engine.today_plan(kp_user.id, size=1)) <= 1

    def test_service_facade(self, service, kp_user):
        assert isinstance(service.today_plan(kp_user.id, size=3), list)
        assert isinstance(service.mastery_profile(kp_user.id), list)
