"""周报与掌握度趋势测试（固定日期，确定性断言）。"""
from __future__ import annotations

import datetime as dt

from backend.services.stats import mastery_trend, weekly_report


class _Q:
    def __init__(self, qid: int, created_at: dt.datetime, tags: list[str]):
        self.id = qid
        self.created_at = created_at
        self.tags = tags
        self.knowledge_points = tags


class _Log:
    def __init__(self, qid: int, reviewed_at: dt.datetime, grade: str, interval: float = 6.0):
        self.question_id = qid
        self.reviewed_at = reviewed_at
        self.grade = grade
        self.next_interval = interval


# 2026-09-09 是周三；本周一为 2026-09-07
_TODAY = dt.date(2026, 9, 9)


def test_weekly_report_counts_this_week_only():
    questions = [
        _Q(1, dt.datetime(2026, 9, 8, 10, 0), ["代数"]),   # 本周二
        _Q(2, dt.datetime(2026, 9, 1, 10, 0), ["几何"]),   # 上周
    ]
    logs = [
        _Log(1, dt.datetime(2026, 9, 9, 9, 0), "good"),
        _Log(1, dt.datetime(2026, 9, 9, 10, 0), "again"),
        _Log(2, dt.datetime(2026, 8, 30, 9, 0), "easy"),  # 上上周
    ]
    report = weekly_report(questions, logs, today=_TODAY)
    assert report == {"created": 1, "reviews": 2, "accuracy": 50, "active_days": 2}


def test_weekly_report_empty_week():
    report = weekly_report([], [], today=_TODAY)
    assert report == {"created": 0, "reviews": 2 - 2, "accuracy": None, "active_days": 0}


def test_mastery_trend_grows_with_reviews():
    created = dt.datetime(2026, 9, 1, 9, 0)
    questions = [_Q(1, created, ["代数"]), _Q(2, created, ["几何"])]
    logs = [
        _Log(1, dt.datetime(2026, 9, 5, 9, 0), "easy", 30.0),
        _Log(2, dt.datetime(2026, 9, 6, 9, 0), "good", 30.0),
    ]
    trend = mastery_trend(questions, logs, days=10, today=_TODAY)

    # 窗口 08-31..09-09 共 10 天，但 08-31 尚无错题 → 9 个点位
    assert len(trend) == 9
    by_date = {p["date"]: p["mastery"] for p in trend}
    assert by_date["09-02"] == 0  # 尚无复习
    assert by_date["09-08"] > by_date["09-02"]  # 复习后掌握度上升


def test_mastery_trend_skips_days_before_creation():
    questions = [_Q(1, dt.datetime(2026, 9, 8, 9, 0), ["代数"])]
    trend = mastery_trend(questions, [], days=5, today=_TODAY)
    # 9/8 之前的日期无错题，不产出点位
    assert all(p["date"] in {"09-08", "09-09"} for p in trend)
