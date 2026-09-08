"""学情统计服务：知识点分布、掌握度、活跃度。

掌握度定义（0~1）：某标签下所有错题的「复习表现加权」，
    无复习记录 → 0（待复习验证）；
    有记录 → good/easy 占比 × 0.7 + 调度间隔归一化 × 0.3。
轻量启发式即可支撑学情看板，避免过度建模。
"""
from __future__ import annotations

import datetime as dt

from backend.models.orm import Question
from backend.models.schemas import TagStat

_GOOD_GRADES = {"good", "easy"}


def build_tag_stats(
    questions: list[Question],
    logs_by_question: dict[int, list[tuple[str, float]]] | None = None,
) -> list[TagStat]:
    """按标签聚合错题数量与掌握度。

    logs_by_question: question_id -> [(grade, interval_days_after_review), ...]
    """
    logs_by_question = logs_by_question or {}
    buckets: dict[str, list[Question]] = {}
    for question in questions:
        for tag in question.tags or []:
            buckets.setdefault(tag, []).append(question)

    stats: list[TagStat] = []
    for tag, members in buckets.items():
        stats.append(
            TagStat(
                tag=tag,
                count=len(members),
                mastery=_tag_mastery(members, logs_by_question),
            )
        )
    stats.sort(key=lambda s: s.count, reverse=True)
    return stats


def _tag_mastery(
    questions: list[Question],
    logs_by_question: dict[int, list[tuple[str, float]]],
) -> float:
    total, success = 0, 0
    interval_sum = 0.0
    for question in questions:
        logs = logs_by_question.get(question.id, [])
        for grade, interval in logs:
            total += 1
            if grade in _GOOD_GRADES:
                success += 1
            interval_sum += min(interval, 60.0)
    if total == 0:
        return 0.0
    success_ratio = success / total
    interval_ratio = min(interval_sum / total / 30.0, 1.0)  # 30 天间隔视为充分巩固
    return round(min(success_ratio * 0.7 + interval_ratio * 0.3, 1.0), 3)


def build_activity(questions: list[Question], days: int = 14) -> list[dict]:
    """近 N 天每日新增错题数，供趋势图使用。"""
    today = dt.date.today()
    counts = {today - dt.timedelta(days=offset): 0 for offset in range(days)}
    for question in questions:
        if question.created_at is None:
            continue
        created = question.created_at
        if created.tzinfo is not None:
            created = created.astimezone().date()
        else:
            created = created.date()
        if created in counts:
            counts[created] += 1
    return [
        {"date": day.strftime("%m-%d"), "count": counts[day]}
        for day in sorted(counts)
    ]


def weak_tags(tag_stats: list[TagStat], limit: int = 5) -> list[TagStat]:
    """掌握度最低且题量不为零的前 N 个标签 —— 「今日最该复习什么」。"""
    candidates = [s for s in tag_stats if s.count > 0]
    candidates.sort(key=lambda s: (s.mastery, -s.count))
    return candidates[:limit]


def study_streak(active_dates: set) -> int:
    """连续学习天数：以今天（若今天无记录则从昨天）向前数，活跃日连续计数。

    active_dates: 学习发生的日期集合（录入错题或完成复习）。
    """
    if not active_dates:
        return 0
    today = dt.date.today()
    normalized = set()
    for value in active_dates:
        if isinstance(value, dt.datetime):
            normalized.add(value.astimezone().date() if value.tzinfo else value.date())
        elif isinstance(value, dt.date):
            normalized.add(value)

    cursor = today if today in normalized else today - dt.timedelta(days=1)
    if cursor not in normalized:
        return 0
    streak = 0
    while cursor in normalized:
        streak += 1
        cursor -= dt.timedelta(days=1)
    return streak
