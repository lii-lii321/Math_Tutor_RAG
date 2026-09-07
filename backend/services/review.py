"""间隔重复复习服务：SM-2 算法（Anki 同源）的简化工业实现。

grade → SM-2 质量 q 映射：
    again → 0（未记牢，重来）
    hard  → 3（勉强记住）
    good  → 4（正常记住）
    easy  → 5（轻松记住）
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from backend.config import Settings, get_settings

GRADE_TO_QUALITY: dict[str, int] = {"again": 0, "hard": 3, "good": 4, "easy": 5}
GRADE_ORDER = ("again", "hard", "good", "easy")
MIN_EASE = 1.3


@dataclass
class ScheduleResult:
    grade: str
    quality: int
    prev_interval: float
    next_interval: float
    ease_after: float
    due_at: dt.datetime

    @property
    def human_interval(self) -> str:
        return format_interval(self.next_interval)


def format_interval(days: float) -> str:
    if days <= 0:
        return "10 分钟后"
    if days < 1:
        minutes = max(1, round(days * 24 * 60))
        return f"{minutes} 分钟后"
    if days < 30:
        return f"{round(days)} 天后"
    months = days / 30
    return f"{months:.1f} 个月后"


class ReviewScheduler:
    """SM-2 调度器：纯函数实现，便于单元测试。"""

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()

    def next_schedule(
        self,
        *,
        grade: str,
        reps: int,
        ease: float,
        interval_days: float,
        now: dt.datetime | None = None,
    ) -> ScheduleResult:
        now = now or dt.datetime.now(dt.timezone.utc)
        if grade not in GRADE_TO_QUALITY:
            raise ValueError(f"未知复习评分: {grade}")

        quality = GRADE_TO_QUALITY[grade]
        prev_interval = interval_days
        new_ease = self._next_ease(ease, quality)

        if quality < 3:
            # 未记牢：重置进度，短间隔后重现
            next_interval = self.settings.review_again_minutes / (24 * 60)
            new_reps = 0
        else:
            new_reps = reps + 1
            if new_reps == 1:
                next_interval = 1.0
            elif new_reps == 2:
                next_interval = 6.0
            else:
                next_interval = max(1.0, round(prev_interval * new_ease))

        due_at = now + dt.timedelta(days=next_interval)
        return ScheduleResult(
            grade=grade,
            quality=quality,
            prev_interval=prev_interval,
            next_interval=next_interval,
            ease_after=new_ease,
            due_at=due_at,
        )

    @staticmethod
    def _next_ease(ease: float, quality: int) -> float:
        new_ease = ease + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
        return round(max(MIN_EASE, new_ease), 4)
