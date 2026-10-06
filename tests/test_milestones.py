"""激励系统单测（批 D / 提升方案 C1+C2）：每日目标读写与里程碑引擎。

全程零 AI 调用：evaluate 直接传 stats 字典，不走 dashboard_stats /
向量库；迁移覆盖由 test_migrations.py 空库 upgrade head 自动兜住。
"""
from __future__ import annotations

import uuid

import pytest

from backend.config import get_settings
from backend.database import session_scope
from backend.models.orm import User, UserMilestone
from backend.services.milestone import (
    MASTERED_1,
    MASTERED_10,
    MASTERED_50,
    STREAK_7,
    TOTAL_100,
    awarded,
    evaluate,
    get_daily_goal,
    set_daily_goal,
)


@pytest.fixture
def goal_user(db_session):
    user = User(username=f"goal_{uuid.uuid4().hex[:8]}", password_hash="x", role="student")
    db_session.add(user)
    db_session.commit()
    return user


def _stats(*, mastered: int = 0, streak: int = 0, total: int = 0) -> dict:
    return {"mastered": mastered, "streak": streak, "total": total}


# ---------- 每日目标 ----------

def test_daily_goal_roundtrip(goal_user):
    assert set_daily_goal(goal_user.id, 5) == 5
    assert get_daily_goal(goal_user.id) == 5
    set_daily_goal(goal_user.id, 200)
    assert get_daily_goal(goal_user.id) == 200


def test_daily_goal_none_falls_back_to_settings_default(goal_user):
    """新用户 daily_goal 为 NULL → 回退 get_settings().daily_goal（env 语义）。"""
    with session_scope() as session:
        assert session.get(User, goal_user.id).daily_goal is None
    assert get_daily_goal(goal_user.id) == get_settings().daily_goal


@pytest.mark.parametrize("bad", [0, 201, -1, "5", True])
def test_daily_goal_rejects_out_of_range(bad, goal_user):
    with pytest.raises(ValueError):
        set_daily_goal(goal_user.id, bad)


# ---------- 里程碑 ----------

def test_evaluate_awards_new_milestone_and_persists(goal_user):
    newly = evaluate(goal_user.id, _stats(mastered=1, total=3))
    assert [spec.code for spec in newly] == [MASTERED_1]
    assert {row["code"] for row in awarded(goal_user.id)} == {MASTERED_1}


def test_evaluate_is_idempotent(goal_user):
    stats = _stats(mastered=1)
    assert evaluate(goal_user.id, stats)  # 首次：新达成
    assert evaluate(goal_user.id, stats) == []  # 二次：返回空
    evaluate(goal_user.id, _stats(mastered=99))  # 更高值补齐 10/50 两枚
    assert evaluate(goal_user.id, _stats(mastered=99)) == []  # 再评不再新增
    with session_scope() as session:
        rows = session.query(UserMilestone).filter_by(user_id=goal_user.id).all()
    assert len(rows) == 3
    codes = [row.code for row in rows]
    assert len(codes) == len(set(codes)) == 3, "同一里程碑不得重复落库"


def test_evaluate_thresholds_chain(goal_user):
    """恰第 10/50 题掌握触发对应里程碑；未达阈值的枚不触发。"""
    first = evaluate(goal_user.id, _stats(mastered=10, total=12))
    assert {spec.code for spec in first} == {MASTERED_1, MASTERED_10}
    second = evaluate(goal_user.id, _stats(mastered=50, total=60))
    assert [spec.code for spec in second] == [MASTERED_50]
    assert evaluate(goal_user.id, _stats(streak=6)) == []  # 差一天不触发
    assert {spec.code for spec in evaluate(goal_user.id, _stats(streak=7))} == {STREAK_7}
    assert TOTAL_100 in {spec.code for spec in evaluate(goal_user.id, _stats(total=100))}


def test_milestones_isolated_between_users(db_session):
    a = User(username=f"iso_a_{uuid.uuid4().hex[:6]}", password_hash="x", role="student")
    b = User(username=f"iso_b_{uuid.uuid4().hex[:6]}", password_hash="x", role="student")
    db_session.add_all([a, b])
    db_session.commit()
    evaluate(a.id, _stats(mastered=1))
    assert {row["code"] for row in awarded(a.id)} == {MASTERED_1}
    assert awarded(b.id) == []
    assert evaluate(b.id, _stats(total=1)) == []
