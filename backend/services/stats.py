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


def build_difficulty_distribution(questions: list[Question]) -> dict[str, int]:
    """难度分布：easy/medium/hard 计数（未知难度归入 medium）。"""
    counts = {"easy": 0, "medium": 0, "hard": 0}
    for question in questions:
        difficulty = (question.difficulty or "medium").lower()
        if difficulty not in counts:
            difficulty = "medium"
        counts[difficulty] += 1
    return counts


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


def study_streak(active_dates: set, today: dt.date | None = None) -> int:
    """连续学习天数：以今天（若今天无记录则从昨天）向前数，活跃日连续计数。

    active_dates: 学习发生的日期或时刻集合（录入错题或完成复习）。
    today: 可注入当前日期，便于测试。
    """
    if not active_dates:
        return 0
    today = today or dt.date.today()
    normalized = {_as_date(value) for value in active_dates}

    cursor = today if today in normalized else today - dt.timedelta(days=1)
    if cursor not in normalized:
        return 0
    streak = 0
    while cursor in normalized:
        streak += 1
        cursor -= dt.timedelta(days=1)
    return streak


def _as_date(value) -> dt.date:
    if isinstance(value, dt.datetime):
        return value.astimezone().date() if value.tzinfo else value.date()
    return value


def build_calendar(events: list, days: int = 90, today: dt.date | None = None) -> dict:
    """GitHub 风格学习日历的矩阵数据。

    返回 {"z": 7×N 矩阵（周一在首行，无数据/未来日期为 None）,
          "x": 每列周一起始日期标签, "y": 星期标签, "max": 峰值}
    """
    today = today or dt.date.today()
    start = today - dt.timedelta(days=days - 1)
    start -= dt.timedelta(days=start.weekday())  # 对齐周一

    counts: dict[dt.date, int] = {}
    for event in events or []:
        day = _as_date(event)
        counts[day] = counts.get(day, 0) + 1

    n_weeks = ((today - start).days + 7) // 7
    z: list[list[int | None]] = [[None] * n_weeks for _ in range(7)]
    dates: list[list[str | None]] = [[None] * n_weeks for _ in range(7)]
    day = start
    while day <= today:
        col = (day - start).days // 7
        z[day.weekday()][col] = counts.get(day, 0)
        dates[day.weekday()][col] = day.isoformat()
        day += dt.timedelta(days=1)

    return {
        "z": z,
        "x": [f"W{w + 1}" for w in range(n_weeks)],
        "y": ["一", "二", "三", "四", "五", "六", "日"],
        "dates": dates,
        "max": max(counts.values(), default=0),
    }


def build_accuracy_trend(logs: list, days: int = 30, today: dt.date | None = None) -> list[dict]:
    """近 N 天复习正确率趋势：仅返回有复习记录的日期。

    正确率 = (good + easy) / 当日复习总数。
    """
    today = today or dt.date.today()
    start = today - dt.timedelta(days=days - 1)
    per_day: dict[dt.date, dict[str, int]] = {}
    for log in logs or []:
        day = _as_date(log.reviewed_at)
        if day < start or day > today:
            continue
        bucket = per_day.setdefault(day, {"total": 0, "strong": 0})
        bucket["total"] += 1
        if log.grade in ("good", "easy"):
            bucket["strong"] += 1

    return [
        {
            "date": day.strftime("%m-%d"),
            "total": bucket["total"],
            "accuracy": round(bucket["strong"] / bucket["total"] * 100),
        }
        for day, bucket in sorted(per_day.items())
    ]


def weekly_report(questions: list, logs: list, today: dt.date | None = None) -> dict:
    """本周（周一起）学习周报 + 上周对比。

    questions/logs 为含 created_at / reviewed_at / grade 属性的鸭子类型。
    返回本周指标（created/reviews/accuracy/active_days）与 prev（上周同口径）。
    """
    today = today or dt.date.today()
    this_monday = today - dt.timedelta(days=today.weekday())
    last_monday = this_monday - dt.timedelta(days=7)

    def _bucket(begin: dt.date, end: dt.date) -> dict:
        created = [q for q in questions if q.created_at and begin <= _as_date(q.created_at) < end]
        reviews = [log for log in logs if begin <= _as_date(log.reviewed_at) < end]
        strong = sum(1 for log in reviews if log.grade in ("good", "easy"))
        active_days = len(
            {_as_date(q.created_at) for q in created}
            | {_as_date(log.reviewed_at) for log in reviews}
        )
        return {
            "created": len(created),
            "reviews": len(reviews),
            "accuracy": round(strong / len(reviews) * 100) if reviews else None,
            "active_days": active_days,
        }

    this_week = _bucket(this_monday, today + dt.timedelta(days=1))
    prev_week = _bucket(last_monday, this_monday)
    return {**this_week, "prev": prev_week}


def mastery_trend(
    questions: list, logs: list, days: int = 30, today: dt.date | None = None
) -> list[dict]:
    """近 N 天整体掌握度变化：按天回放「截至当日」的错题与复习记录。

    掌握度 = 各标签掌握度的简单平均（与看板口径一致），百分制。
    """
    today = today or dt.date.today()
    start = today - dt.timedelta(days=days - 1)
    points: list[dict] = []
    for offset in range(days):
        day = start + dt.timedelta(days=offset)
        qs = [q for q in questions if q.created_at and _as_date(q.created_at) <= day]
        if not qs:
            continue
        day_logs: dict[int, list[tuple[str, float]]] = {}
        for log in logs:
            if _as_date(log.reviewed_at) <= day:
                day_logs.setdefault(log.question_id, []).append(
                    (log.grade, log.next_interval)
                )
        if not day_logs:
            points.append({"date": day.strftime("%m-%d"), "mastery": 0})
            continue
        stats = build_tag_stats(qs, day_logs)
        avg = sum(s.mastery for s in stats) / len(stats)
        points.append({"date": day.strftime("%m-%d"), "mastery": round(avg * 100)})
    return points
