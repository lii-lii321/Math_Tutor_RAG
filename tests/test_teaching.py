"""教学闭环 MVP 测试（提升项 #12）：诊断→练习→作答→延迟复测→归档。"""
from __future__ import annotations

import datetime as dt
import json
import uuid

import pytest

from backend.database import SessionLocal
from backend.models.orm import Question, User
from backend.services.question_service import QuestionService
from backend.services.teaching import TeachingService

_KP = "二次函数的图象与性质"


@pytest.fixture
def service():
    return TeachingService(session_factory=SessionLocal)


@pytest.fixture
def student_user(db_session):
    """专属学生用户：共享 demo 用户会被其他文件的同知识点题串扰（计数不隔离）。"""
    user = User(
        username=f"teach_{uuid.uuid4().hex[:8]}", password_hash="x", role="student"
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def kp_questions(student_user):
    """带目标知识点的两道错题（走服务层，建 M2M 关联）。"""
    q_service = QuestionService(session_factory=SessionLocal)
    q1 = q_service.create_manual_question(
        student_user.id,
        content_markdown="求 y=2x²-8x+1 的顶点坐标",
        answer="顶点 (2, -7)",
        knowledge_points=[_KP],
    )
    q2 = q_service.create_manual_question(
        student_user.id,
        content_markdown="抛物线 y=x²-1 与 x 轴交点个数问题",
        answer="两个",
        knowledge_points=[_KP],
    )
    return q1, q2


def test_full_teaching_loop(service, student_user, kp_questions):
    """全链路：诊断 → 练习登记 → 独立作答通过 → 复测约定 → 复测通过归档。"""
    q1, q2 = kp_questions

    diagnosis = service.start_intervention(student_user.id, _KP)
    assert diagnosis["intervention_id"] > 0
    assert diagnosis["knowledge_point"] == _KP
    assert diagnosis["strategy"] in {"weak_drill", "error_cause", "maintenance"}
    assert {q1.id, q2.id} <= set(diagnosis["question_ids"])
    assert diagnosis["question_count"] == 2

    iid = diagnosis["intervention_id"]
    practiced = service.record_practice(iid, student_user.id, [q1.id], variant_source_id=q2.id)
    assert practiced["outcome"] == "practiced"
    assert practiced["question_ids"] == [q1.id]
    assert practiced["variant_source_id"] == q2.id

    scheduled = service.record_outcome(iid, student_user.id, passed=True)
    assert scheduled["outcome"] == "retest_scheduled"
    assert scheduled["retest_due_at"] is not None  # 约定 7 天后复测
    due = dt.datetime.fromisoformat(scheduled["retest_due_at"])
    assert due > dt.datetime.now(dt.timezone.utc)

    retest = service.record_retest(iid, student_user.id, passed=True, question_id=q1.id)
    assert retest["outcome"] == "retest_passed"

    # 复测通过：题目落 retest_verified_at（mastered 门槛的复测半边）
    with SessionLocal() as session:
        question = session.get(Question, q1.id)
        assert question.retest_verified_at is not None

    history = service.history(student_user.id)
    assert any(row["id"] == iid and row["outcome"] == "retest_passed" for row in history)


def test_mastered_requires_retest_verification(student_user, kp_questions):
    """SM-2 达标但未复测 → 不归档；复测通过 → 归档（单次答对 ≠ 掌握）。"""
    q1, _ = kp_questions
    with SessionLocal() as session:
        question = session.get(Question, q1.id)
        question.reps = 3
        question.interval_days = 21
        session.commit()

    service = QuestionService(session_factory=SessionLocal)
    fresh = service.get_question(q1.id, student_user.id)
    assert fresh.reps >= 3 and fresh.interval_days >= 21
    assert fresh.mastered is False  # 缺复测确认

    with SessionLocal() as session:
        question = session.get(Question, q1.id)
        question.retest_verified_at = dt.datetime.now(dt.timezone.utc)
        session.commit()

    verified = service.get_question(q1.id, student_user.id)
    assert verified.mastered is True


def test_mastery_delta_measures_intervention_effect(service, student_user, kp_questions):
    """干预有效性对比（1.2）：诊断前无日志 → before=0.2 基线；评分后 after 上移。"""
    from backend.services.question_service import QuestionService

    q1, _ = kp_questions
    diagnosis = service.start_intervention(student_user.id, _KP)
    iid = diagnosis["intervention_id"]
    service.record_practice(iid, student_user.id, [q1.id])

    delta = service.mastery_delta(iid, student_user.id)
    assert delta is not None
    assert delta["before"] == pytest.approx(0.2, abs=0.01), "诊断前无日志按未复习基线"
    assert delta["after"] == pytest.approx(0.2, abs=0.01)
    assert delta["reviewed_after"] == 0

    q_service = QuestionService(session_factory=SessionLocal)
    # created_at/reviewed_at 在 SQLite 都是秒级精度（server_default=func.now()）：
    # 诊断与评分必须跨秒，否则评分日志落进「诊断时点」边界导致 before 失真
    import time as _time

    _time.sleep(1.1)
    q_service.grade_review(q1.id, student_user.id, "good")

    delta = service.mastery_delta(iid, student_user.id)
    assert delta["after"] > delta["before"], "复习后掌握度应上移"
    assert delta["reviewed_after"] == 1
    assert delta["delta"] == pytest.approx(delta["after"] - delta["before"], abs=0.001)


def test_mastery_delta_none_for_stranger(service, student_user, kp_questions):
    from backend.models.orm import User

    with SessionLocal() as session:
        stranger = User(
            username=f"md_stranger_{uuid.uuid4().hex[:6]}", password_hash="x", role="student"
        )
        session.add(stranger)
        session.commit()
        stranger_id = stranger.id
    diagnosis = service.start_intervention(student_user.id, _KP)
    assert service.mastery_delta(diagnosis["intervention_id"], stranger_id) is None


def test_state_machine_and_ownership(service, student_user, kp_questions):
    """状态机非法迁移与跨用户访问按业务错误拒绝。"""
    q1, _ = kp_questions
    diagnosis = service.start_intervention(student_user.id, _KP)
    iid = diagnosis["intervention_id"]

    # 跳步：diagnosed 直接登记复测 → 拒绝
    with pytest.raises(ValueError, match="不允许登记复测"):
        service.record_retest(iid, student_user.id, passed=True, question_id=q1.id)

    # 跨用户访问 → 拒绝
    with SessionLocal() as session:
        from backend.models.orm import User

        stranger = User(username="teaching_stranger", password_hash="x", role="student")
        session.add(stranger)
        session.commit()
        stranger_id = stranger.id
    with pytest.raises(ValueError, match="不存在或无权"):
        service.record_practice(iid, stranger_id, [q1.id])

    # 未通过作答：保持 practiced 可再练
    service.record_practice(iid, student_user.id, [q1.id])
    failed = service.record_outcome(iid, student_user.id, passed=False)
    assert failed["outcome"] == "practiced"


def test_unknown_kp_rejected(service, student_user):
    with pytest.raises(ValueError, match="不存在知识点"):
        service.start_intervention(student_user.id, "不存在的知识点_xyz")


def test_agent_tool_retest_requires_confirm(student_user, kp_questions):
    """Agent 工具：复测登记走写操作确认门；start_kp_intervention 免确认（诊断只读语义）。"""
    from backend.services.agent import AgentSession

    q1, _ = kp_questions
    session = AgentSession(user_id=student_user.id)

    diagnosis = json.loads(
        session._execute_tool(
            "start_kp_intervention",
            json.dumps({"knowledge_point": _KP}),
        )
    )
    assert diagnosis["intervention_id"] > 0

    # 先推到 retest_scheduled（经服务层，工具无对应写方法属 MVP 边界）
    teaching = TeachingService(session_factory=SessionLocal)
    teaching.record_practice(diagnosis["intervention_id"], student_user.id, [q1.id])
    teaching.record_outcome(diagnosis["intervention_id"], student_user.id, passed=True)

    denied = session._execute_tool(
        "record_retest_outcome",
        json.dumps(
            {
                "intervention_id": diagnosis["intervention_id"],
                "question_id": q1.id,
                "passed": True,
            }
        ),
    )
    assert denied.startswith("ERROR[param]")

    done = session._execute_tool(
        "record_retest_outcome",
        json.dumps(
            {
                "intervention_id": diagnosis["intervention_id"],
                "question_id": q1.id,
                "passed": True,
                "confirm": True,
            }
        ),
    )
    assert done.startswith("{") and '"retest_passed"' in done
