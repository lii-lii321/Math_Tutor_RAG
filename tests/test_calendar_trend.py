"""学习日历与正确率趋势的纯函数测试。"""
from __future__ import annotations

import datetime as dt

from backend.services.stats import build_accuracy_trend, build_calendar


class FakeLog:
    def __init__(self, reviewed_at: dt.datetime, grade: str):
        self.reviewed_at = reviewed_at
        self.grade = grade


def test_calendar_shapes_and_counts():
    today = dt.date(2026, 9, 12)  # 周六
    events = [
        dt.datetime(2026, 9, 12, 10, 0),
        dt.datetime(2026, 9, 12, 11, 0),
        dt.datetime(2026, 9, 11, 9, 0),
    ]
    calendar = build_calendar(events, days=90, today=today)
    assert len(calendar["z"]) == 7
    assert len(calendar["x"]) == len(calendar["z"][0])
    assert calendar["max"] == 2
    # 行索引 0=周一..6=周日；9/11 是周五（row 4）1 次，9/12 是周六（row 5）2 次
    assert calendar["z"][4][-1] == 1  # 周五
    assert calendar["z"][5][-1] == 2  # 周六


def test_calendar_future_cells_are_none():
    today = dt.date(2026, 9, 12)  # 周六：最后一列的周日（row 6）尚未到来
    calendar = build_calendar([dt.datetime(2026, 9, 12)], days=90, today=today)
    assert calendar["z"][6][-1] is None  # 周日是未来 → None
    assert calendar["z"][5][-1] == 1  # 周六今天有 1 次
    assert calendar["z"][0][-1] == 0  # 本周一已过去且无记录 → 0


def test_calendar_empty_events_all_zero():
    calendar = build_calendar([], days=14, today=dt.date(2026, 9, 12))
    flat = [cell for row in calendar["z"] for cell in row if cell is not None]
    assert calendar["max"] == 0
    assert set(flat) == {0}


def test_accuracy_trend_groups_and_ratio():
    day = dt.datetime(2026, 9, 12, 10, 0)
    logs = [
        FakeLog(day, "good"),
        FakeLog(day + dt.timedelta(hours=1), "easy"),
        FakeLog(day + dt.timedelta(hours=2), "again"),
        FakeLog(day - dt.timedelta(days=40), "good"),  # 窗口外应被忽略
    ]
    trend = build_accuracy_trend(logs, days=30)
    assert len(trend) == 1
    assert trend[0]["total"] == 3
    assert trend[0]["accuracy"] == 67  # 2/3


def test_accuracy_trend_empty_window():
    assert build_accuracy_trend([], days=30) == []
