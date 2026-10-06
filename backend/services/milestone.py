"""激励系统（批 D / 提升方案 C1+C2）：每日目标读写与里程碑引擎。

- 每日目标存 users.daily_goal（可空），None 回退 get_settings().daily_goal，
  1-200 校验与 config.py:35 的 ge/le 同源；
- 里程碑为文档 C2 全集六枚（掌握 1/10/50、连续 7/30 天、累计 100 题），
  evaluate 复用 dashboard_stats 的 total/mastered/streak 统计免二次查询，
  先查已达成集合仅插新增——幂等，达成一次不重复触发。
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select

from backend.config import get_settings
from backend.database import session_scope
from backend.models.orm import User, UserMilestone
from backend.utils.logging import get_logger

logger = get_logger("milestones")

MASTERED_1 = "mastered_1"
MASTERED_10 = "mastered_10"
MASTERED_50 = "mastered_50"
STREAK_7 = "streak_7"
STREAK_30 = "streak_30"
TOTAL_100 = "total_100"


@dataclass(frozen=True)
class MilestoneSpec:
    """一枚里程碑：code 落库标识，metric 取 dashboard_stats 的键。"""

    code: str
    label: str
    metric: str  # mastered / streak / total
    threshold: int


MILESTONES: tuple[MilestoneSpec, ...] = (
    MilestoneSpec(MASTERED_1, "🏆 初次掌握", "mastered", 1),
    MilestoneSpec(MASTERED_10, "🏆 掌握 10 题", "mastered", 10),
    MilestoneSpec(MASTERED_50, "🏆 掌握 50 题", "mastered", 50),
    MilestoneSpec(STREAK_7, "🔥 连续学习 7 天", "streak", 7),
    MilestoneSpec(STREAK_30, "🔥 连续学习 30 天", "streak", 30),
    MilestoneSpec(TOTAL_100, "📚 累计 100 题", "total", 100),
)

_SPEC_BY_CODE = {spec.code: spec for spec in MILESTONES}


def set_daily_goal(user_id: int, goal: int) -> int:
    """写入用户每日目标（1-200，与 config.daily_goal 的 ge/le 同源）。"""
    if isinstance(goal, bool) or not isinstance(goal, int) or not 1 <= goal <= 200:
        raise ValueError("每日目标需为 1-200 的整数")
    with session_scope() as session:
        user = session.get(User, user_id)
        if user is None:
            raise ValueError("用户不存在")
        user.daily_goal = goal
    logger.info("用户 %s 每日目标设为 %s", user_id, goal)
    return goal


def get_daily_goal(user_id: int) -> int:
    """读取生效每日目标；未设置（NULL / 用户不存在）回退全局默认。"""
    with session_scope() as session:
        user = session.get(User, user_id)
        goal = user.daily_goal if user is not None else None
    return goal if goal is not None else get_settings().daily_goal


def evaluate(user_id: int, stats: dict | None = None) -> list[MilestoneSpec]:
    """按看板统计评估里程碑，返回本轮新达成的枚集（幂等：已达成不重复）。

    stats 缺省时现场取 QuestionService.dashboard_stats；调用方（看板）
    已加载 stats 时传入以免二次查询。返回值仅供 toast 展示。
    """
    if stats is None:
        from backend.services.question_service import QuestionService

        stats = QuestionService().dashboard_stats(user_id)

    achieved_codes = {row["code"] for row in awarded(user_id)}
    newly = [
        spec
        for spec in MILESTONES
        if spec.code not in achieved_codes
        and stats.get(spec.metric, 0) >= spec.threshold
    ]
    if not newly:
        return []
    with session_scope() as session:
        # 双重保险：并发评估下唯一约束兜底，重查一遍避免撞 uq_user_milestone
        existing = set(
            session.execute(
                select(UserMilestone.code).where(UserMilestone.user_id == user_id)
            ).scalars()
        )
        for spec in newly:
            if spec.code in existing:
                continue
            session.add(UserMilestone(user_id=user_id, code=spec.code))
    logger.info(
        "用户 %s 新达成里程碑：%s", user_id, [spec.code for spec in newly]
    )
    return newly


def awarded(user_id: int) -> list[dict]:
    """已达成里程碑（新→旧），供看板徽章墙渲染。"""
    with session_scope() as session:
        rows = (
            session.execute(
                select(UserMilestone)
                .where(UserMilestone.user_id == user_id)
                .order_by(UserMilestone.achieved_at.desc(), UserMilestone.id.desc())
            )
            .scalars()
            .all()
        )
    return [
        {
            "code": row.code,
            "achieved_at": row.achieved_at,
            "label": _SPEC_BY_CODE[row.code].label if row.code in _SPEC_BY_CODE else row.code,
        }
        for row in rows
    ]
