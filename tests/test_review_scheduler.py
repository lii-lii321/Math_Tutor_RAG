from __future__ import annotations

import pytest

from backend.services.review import ReviewScheduler, format_interval_short
from backend.utils.security import hash_password


@pytest.fixture
def scheduler():
    return ReviewScheduler()


def test_first_good_review(scheduler):
    result = scheduler.next_schedule(grade="good", reps=0, ease=2.5, interval_days=0)
    assert result.quality == 4
    assert result.next_interval == 1.0
    assert result.ease_after == 2.5  # q=4 时 ease 不变: 0.1 - 1*0.08 - 1*0.02 = 0


def test_second_good_review_six_days(scheduler):
    result = scheduler.next_schedule(grade="good", reps=1, ease=2.5, interval_days=1)
    assert result.next_interval == 6.0


def test_good_review_grows_interval_by_ease(scheduler):
    result = scheduler.next_schedule(grade="good", reps=2, ease=2.5, interval_days=6)
    assert result.next_interval == 15  # round(6 * 2.5)


def test_easy_increases_ease(scheduler):
    result = scheduler.next_schedule(grade="easy", reps=2, ease=2.5, interval_days=6)
    assert result.ease_after > 2.5


def test_again_resets_progress(scheduler):
    result = scheduler.next_schedule(grade="again", reps=5, ease=2.5, interval_days=30)
    assert result.quality == 0
    assert result.next_interval < 1  # 10 分钟
    assert result.ease_after < 2.5


# ---------- 评分按钮内嵌间隔预告（体验专项 C3） ----------

def test_format_interval_short_buckets():
    assert format_interval_short(0) == "10分钟"
    assert format_interval_short(10 / (24 * 60)) == "10分钟"
    assert format_interval_short(1) == "明天"
    assert format_interval_short(6) == "6天"
    assert format_interval_short(15) == "15天"
    assert format_interval_short(75) == "2.5个月"


def test_format_interval_short_covers_scheduler_outputs(scheduler):
    """四档评分的典型调度输出都能给出可读预告。"""
    cases = [
        scheduler.next_schedule(grade="again", reps=3, ease=2.5, interval_days=15),
        scheduler.next_schedule(grade="hard", reps=0, ease=2.5, interval_days=0),
        scheduler.next_schedule(grade="good", reps=1, ease=2.5, interval_days=1),
        scheduler.next_schedule(grade="easy", reps=4, ease=2.6, interval_days=60),
    ]
    shorts = [format_interval_short(c.next_interval) for c in cases]
    assert all(s and len(s) <= 8 for s in shorts), shorts


def test_hard_keeps_progress_with_reduced_ease(scheduler):
    # 经典 SM-2：q=3 仍算成功复习，间隔继续增长，但 ease 下降使后续增速放缓
    result = scheduler.next_schedule(grade="hard", reps=2, ease=2.5, interval_days=6)
    assert result.quality == 3
    assert result.next_interval > 6
    assert result.ease_after < 2.5


def test_ease_never_below_floor(scheduler):
    result = scheduler.next_schedule(grade="again", reps=0, ease=1.3, interval_days=1)
    assert result.ease_after >= 1.3


def test_unknown_grade_rejected(scheduler):
    with pytest.raises(ValueError):
        scheduler.next_schedule(grade="perfect", reps=0, ease=2.5, interval_days=0)


def test_password_hash_helper_importable():
    assert hash_password("x", rounds=4)
