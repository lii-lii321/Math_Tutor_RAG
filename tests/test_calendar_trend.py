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
    # today 固定为夹具日期：不传则窗口随真实日期滚动，30 天后本用例必然过期
    trend = build_accuracy_trend(logs, days=30, today=dt.date(2026, 9, 12))
    assert len(trend) == 1
    assert trend[0]["total"] == 3
    assert trend[0]["accuracy"] == 67  # 2/3


def test_accuracy_trend_empty_window():
    assert build_accuracy_trend([], days=30) == []


# ---------- 统计日界按应用时区分日（提升项 #5） ----------

def test_as_date_converts_utc_to_app_timezone():
    """UTC 17:00 = 北京次日 01:00：深夜学习必须记到北京的「明天」。"""
    from backend.services.stats import _as_date

    utc_evening = dt.datetime(2026, 10, 12, 17, 0, tzinfo=dt.timezone.utc)
    assert _as_date(utc_evening) == dt.date(2026, 10, 13)

    utc_morning = dt.datetime(2026, 10, 12, 2, 0, tzinfo=dt.timezone.utc)
    assert _as_date(utc_morning) == dt.date(2026, 10, 12)  # 北京 10:00 同日


def test_as_date_naive_passthrough():
    from backend.services.stats import _as_date

    naive = dt.datetime(2026, 10, 12, 23, 0)
    assert _as_date(naive) == dt.date(2026, 10, 12)
    assert _as_date(dt.date(2026, 10, 12)) == dt.date(2026, 10, 12)


def test_accuracy_trend_buckets_by_app_timezone():
    """UTC 服务器部署下，北京时间次日凌晨的复习计入次日分桶。"""
    utc_evening = dt.datetime(2026, 10, 12, 17, 0, tzinfo=dt.timezone.utc)  # 北京 10-13 01:00
    trend = build_accuracy_trend(
        [FakeLog(utc_evening, "good")], days=1, today=dt.date(2026, 10, 13)
    )
    assert len(trend) == 1
    assert trend[0]["total"] == 1


def test_app_timezone_setting_rejects_invalid_name():
    import pytest as _pytest
    from pydantic import ValidationError

    from backend.config import Settings

    with _pytest.raises(ValidationError):
        Settings.model_validate({"app_timezone": "Not/AZone"})
