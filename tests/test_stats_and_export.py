from __future__ import annotations

from datetime import datetime, timedelta, timezone

from backend.models.schemas import QuestionOut
from backend.services.export import generate_word_exam
from backend.services.stats import build_activity, build_tag_stats, study_streak, weak_tags


def _question(idx: int, tags: list[str], due_at=None, reps: int = 0) -> QuestionOut:
    return QuestionOut(
        id=idx,
        user_id=1,
        image_path=None,
        content_markdown=f"题目 {idx} 的解析内容",
        answer="answer",
        knowledge_points=tags,
        tags=tags,
        created_at=datetime.now(timezone.utc),
        due_at=due_at,
        reps=reps,
    )


def test_word_export_produces_docx():
    questions = [_question(1, ["几何"]), _question(2, ["代数"])]
    stream = generate_word_exam(questions, "测试卷")
    data = stream.getvalue()
    assert data[:2] == b"PK"  # docx 本质是 zip
    assert len(data) > 1000


def test_tag_stats_counts_and_mastery_default_zero():
    questions = [_question(1, ["几何"]), _question(2, ["几何", "代数"])]
    stats = build_tag_stats(questions)
    by_tag = {s.tag: s for s in stats}
    assert by_tag["几何"].count == 2
    assert by_tag["代数"].count == 1
    assert by_tag["几何"].mastery == 0.0  # 未复习 → 掌握度 0


def test_mastery_reflects_review_success():
    questions = [_question(1, ["几何"])]
    logs = {1: [("good", 6.0), ("good", 12.0), ("again", 0)]}
    stats = build_tag_stats(questions, logs)
    assert 0.3 < stats[0].mastery < 1.0


def test_weak_tags_orders_by_mastery():
    questions = [_question(1, ["强项"]), _question(2, ["弱项"])]
    logs = {1: [("easy", 30.0)], 2: [("again", 0)]}
    stats = build_tag_stats(questions, logs)
    weak = weak_tags(stats)
    assert weak[0].tag == "弱项"


def test_activity_window_has_14_days():
    now = datetime.now(timezone.utc)
    recent = QuestionOut(
        **{
            **_question(9, []).model_dump(),
            "created_at": now - timedelta(days=1),
        }
    )
    old = QuestionOut(
        **{
            **_question(10, []).model_dump(),
            "created_at": now - timedelta(days=40),
        }
    )
    activity = build_activity([recent, old])
    assert len(activity) == 14
    assert sum(a["count"] for a in activity) == 1  # 只统计近 14 天


def test_study_streak_counts_back_from_today():
    today = datetime.now(timezone.utc).date()
    dates = {today, today - timedelta(days=1), today - timedelta(days=2)}
    assert study_streak(dates) == 3


def test_study_streak_breaks_on_gap():
    today = datetime.now(timezone.utc).date()
    dates = {today, today - timedelta(days=1), today - timedelta(days=3)}
    assert study_streak(dates) == 2


def test_study_streak_allows_yesterday_start():
    today = datetime.now(timezone.utc).date()
    dates = {today - timedelta(days=1), today - timedelta(days=2)}
    assert study_streak(dates) == 2  # 今天还没学，从昨天起算


def test_study_streak_empty():
    assert study_streak(set()) == 0


def test_study_streak_accepts_datetime_and_date_mix():
    now = datetime.now(timezone.utc)
    today = now.date()
    dates = {now, today - timedelta(days=1)}
    assert study_streak(dates) == 2
