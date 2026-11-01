"""教师工作台聚合服务测试：口径、拖期、干预复测窗口、动态、引导态。"""
from __future__ import annotations

import datetime as dt
import uuid

import pytest

from backend.database import SessionLocal
from backend.models.orm import Question, User
from backend.services.class_service import ClassService
from backend.services.question_service import QuestionService
from backend.services.teaching import TeachingService
from backend.services.workbench import TeacherWorkbenchService

_KP = "有理数的乘法（1）"


@pytest.fixture
def wb():
    return TeacherWorkbenchService(session_factory=SessionLocal)


def _make_user(db_session, role: str) -> User:
    user = User(username=f"wb_{role}_{uuid.uuid4().hex[:8]}", password_hash="x", role=role)
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _seed_question(student_id: int, content: str, kp: str, *, due_at=None) -> Question:
    q = QuestionService(session_factory=SessionLocal).create_manual_question(
        student_id, content_markdown=content, answer="x=1", knowledge_points=[kp]
    )
    if due_at is not None:
        with SessionLocal() as session:
            row = session.get(Question, q.id)
            row.due_at = due_at
            session.commit()
    return q


def test_no_class_teacher_gets_onboarding(wb, db_session):
    """未建班教师：onboarding 视图（与 2026-10-25 可见范围收口一致）。"""
    teacher = _make_user(db_session, "teacher")
    data = wb.overview(teacher.id)
    assert data["has_class"] is False
    assert data["students"] == []
    assert data["totals"]["students"] == 0


def test_workbench_due_overdue_and_activity(wb, db_session):
    """到期/拖期分档（超 3 天为拖期）与最近动态（录入+复习合并）。"""
    now = dt.datetime.now(dt.timezone.utc)
    teacher = _make_user(db_session, "teacher")
    student = _make_user(db_session, "student")
    class_service = ClassService()
    klass = class_service.create_class(teacher.id, "工作台班")
    class_service.add_student(teacher.id, klass["id"], student.id)

    _seed_question(
        student.id, "工作台拖期题 overdue_probe", _KP, due_at=now - dt.timedelta(days=10)
    )
    _seed_question(
        student.id, "工作台普通到期题 due_probe", _KP, due_at=now - dt.timedelta(days=1)
    )
    _seed_question(
        student.id, "工作台未来题 future_probe", _KP, due_at=now + dt.timedelta(days=5)
    )
    # 动态探针题单独评分（评分会把该题重排出到期池——不能拿拖期题评分）
    activity_q = _seed_question(student.id, "工作台动态题 activity_probe", _KP)

    svc = QuestionService(session_factory=SessionLocal)
    svc.grade_review(activity_q.id, student.id, "good")  # 制造一条复习动态

    data = wb.overview(teacher.id)
    assert data["has_class"] is True
    assert data["totals"]["students"] == 1
    assert data["totals"]["due"] == 2, "未来到期题与已重排题不计入待复习"
    assert data["totals"]["overdue"] == 1, "拖期线 = 到期超 3 天"
    row = data["students"][0]
    assert row["username"] == student.username
    assert row["due"] == 2 and row["overdue"] == 1
    assert row["weak_kps"], "薄弱知识点应随行返回"

    kinds = {item["kind"] for item in data["activity"]}
    assert {"录入", "复习"} <= kinds


def test_intervention_retest_window_flags(wb, db_session):
    """复测窗口分档：约定时间 3 天内 → due_soon；逾期 → 逾期标记。"""
    now = dt.datetime.now(dt.timezone.utc)
    teacher = _make_user(db_session, "teacher")
    student = _make_user(db_session, "student")
    class_service = ClassService()
    klass = class_service.create_class(teacher.id, "复测窗口班")
    class_service.add_student(teacher.id, klass["id"], student.id)

    q = _seed_question(student.id, "复测窗口探针题 retest_probe", _KP)

    teaching = TeachingService(session_factory=SessionLocal)
    diag = teaching.start_intervention(student.id, _KP)
    teaching.record_practice(diag["intervention_id"], student.id, [q.id])
    teaching.record_outcome(diag["intervention_id"], student.id, passed=True)
    # 教学服务固定 +7 天：直接把约定时间改成 2 天后验证 due_soon 分档
    with SessionLocal() as session:
        from backend.models.orm import TeachingIntervention

        record = session.get(TeachingIntervention, diag["intervention_id"])
        assert record.outcome == "retest_scheduled"
        record.retest_due_at = now + dt.timedelta(days=2)
        session.commit()

    data = wb.overview(teacher.id)
    assert data["totals"]["retest_due"] == 1
    item = next(x for x in data["interventions"] if x["id"] == diag["intervention_id"])
    assert item["window"].startswith("复测窗口")
    assert item["student"] == student.username

    # 逾期档：把约定时间拨到 5 天前
    with SessionLocal() as session:
        from backend.models.orm import TeachingIntervention

        record = session.get(TeachingIntervention, diag["intervention_id"])
        record.retest_due_at = now - dt.timedelta(days=5)
        session.commit()
    data = wb.overview(teacher.id)
    item = next(x for x in data["interventions"] if x["id"] == diag["intervention_id"])
    assert item["window"].startswith("复测已逾期")
    assert data["totals"]["retest_due"] == 1


def test_out_of_scope_student_not_leaked(wb, db_session):
    """班外学生的题目与干预不得出现在工作台（多租户口径延续）。"""
    teacher = _make_user(db_session, "teacher")
    outsider = _make_user(db_session, "student")
    _seed_question(outsider.id, "班外探针题 outside_probe", _KP)
    class_service = ClassService()
    klass = class_service.create_class(teacher.id, "不含班外生班")
    insider = _make_user(db_session, "student")
    class_service.add_student(teacher.id, klass["id"], insider.id)
    _seed_question(insider.id, "班内探针题 inside_probe", _KP)

    data = wb.overview(teacher.id)
    assert [r["username"] for r in data["students"]] == [insider.username]
    assert all("outside_probe" not in item["text"] for item in data["activity"])
