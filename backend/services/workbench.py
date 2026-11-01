"""教师工作台聚合服务：以「今天该做什么」为核心的跨学生操作视图。

与既有页面的分工：
- 学生总览（students_overview）= 报表视角：一段时间内学生学得怎么样；
- 工作台（本服务）= 操作视角：现在有什么要处理——到期/拖期复习、
  干预与复测窗口、最近动态、快捷入口。

可见范围口径与 2026-10-25 收口一致：教师可见 = 自己 + 所教班级学生；
未建班 = 空学生视图 + 引导建班（onboarding）。
"""
from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Iterator
from contextlib import contextmanager

from sqlalchemy import and_, func, not_, or_, select
from sqlalchemy.orm import Session, sessionmaker

from backend.models.orm import Question, ReviewLog, TeachingIntervention, User
from backend.services.class_service import ClassService
from backend.services.teaching import TeachingService
from backend.utils.logging import get_logger

logger = get_logger(__name__)

# 拖期线：到期超过 N 天仍未复习（比「到期」更强的关注信号）
OVERDUE_AFTER_DAYS = 3
# 复测临近线：约定复测时间在 N 天内（含逾期）
RETEST_SOON_DAYS = 3
# 进行中的干预状态机状态
_ACTIVE_OUTCOMES = ("diagnosed", "practiced", "retest_scheduled")
_GRADE_LABELS = {"again": "忘了", "hard": "勉强", "good": "记得", "easy": "秒懂"}

# SM-2 达标 + 复测通过 = 掌握归档（与 QuestionOut.mastered 同口径，SQL 可表达）
_MASTERED_SQL = and_(
    Question.reps >= 3,
    Question.interval_days >= 21,
    Question.retest_verified_at.is_not(None),
)


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class TeacherWorkbenchService:
    """跨学生操作视图聚合：全部只读，单次 overview 一次会话完成主要查询。"""

    def __init__(
        self,
        session_factory: sessionmaker | Callable[[], Iterator[Session]] | None = None,
    ):
        self._session_factory = session_factory

    @contextmanager
    def _session(self) -> Iterator[Session]:
        from backend.database import session_scope

        with session_scope(self._session_factory) as session:
            yield session

    def overview(self, teacher_id: int) -> dict:
        """教师工作台全景。未建班返回 onboarding 视图（空学生 + 引导）。"""
        class_service = ClassService()
        has_class = class_service.has_classes(teacher_id)
        scope = [teacher_id]
        if has_class:
            scope += class_service.student_ids_for_teacher(teacher_id)

        result: dict = {
            "has_class": has_class,
            "students": [],
            "totals": {"students": 0, "due": 0, "overdue": 0, "retest_due": 0, "in_progress": 0},
            "interventions": [],
            "activity": [],
        }
        if not has_class:
            return result

        now = _now()
        overdue_line = now - dt.timedelta(days=OVERDUE_AFTER_DAYS)
        due_cond = and_(
            Question.user_id.in_(scope),
            or_(Question.due_at.is_(None), Question.due_at <= now),
            not_(_MASTERED_SQL),
        )

        with self._session() as session:
            due_rows = session.execute(
                select(Question.user_id, func.count()).where(due_cond).group_by(Question.user_id)
            ).all()
            overdue_rows = session.execute(
                select(Question.user_id, func.count())
                .where(and_(due_cond, Question.due_at < overdue_line))
                .group_by(Question.user_id)
            ).all()
            interventions = (
                session.execute(
                    select(TeachingIntervention)
                    .where(
                        TeachingIntervention.user_id.in_(scope),
                        TeachingIntervention.outcome.in_(_ACTIVE_OUTCOMES),
                    )
                    .order_by(
                        TeachingIntervention.retest_due_at.asc().nulls_last(),
                        TeachingIntervention.created_at.desc(),
                    )
                    .limit(20)
                )
                .scalars()
                .all()
            )
            recent_questions = (
                session.execute(
                    select(Question)
                    .where(Question.user_id.in_(scope))
                    .order_by(Question.created_at.desc())
                    .limit(12)
                )
                .scalars()
                .all()
            )
            recent_logs = (
                session.execute(
                    select(ReviewLog)
                    .where(ReviewLog.user_id.in_(scope))
                    .order_by(ReviewLog.reviewed_at.desc())
                    .limit(12)
                )
                .scalars()
                .all()
            )
            usernames = dict(
                session.execute(select(User.id, User.username).where(User.id.in_(scope))).all()
            )

        due_map = {uid: int(n) for uid, n in due_rows}
        overdue_map = {uid: int(n) for uid, n in overdue_rows}

        # 学生行：学生总览（已按班级收口）为基础，叠加拖期与薄弱知识点
        from backend.services.mastery import MasteryEngine
        from backend.services.question_service import QuestionService

        rows = QuestionService(session_factory=self._session_factory).students_overview(teacher_id)
        mastery_engine = MasteryEngine(self._session_factory)
        for row in rows:
            uid = row["user_id"]
            row["due"] = due_map.get(uid, 0)
            row["overdue"] = overdue_map.get(uid, 0)
            weak = [
                item.knowledge_point
                for item in mastery_engine.profile(uid)
                if item.status != "solid"
            ][:2]
            row["weak_kps"] = weak
        rows.sort(key=lambda r: (-r["due"], r["username"]))

        # 干预与复测窗口
        interventions_out: list[dict] = []
        retest_due = 0
        teaching_service = TeachingService(self._session_factory)
        for record in interventions:
            due_at = record.retest_due_at
            window = ""
            if record.outcome == "retest_scheduled" and due_at is not None:
                if due_at.tzinfo is None:
                    due_at = due_at.replace(tzinfo=dt.timezone.utc)
                if due_at < now:
                    window = f"复测已逾期 {(now - due_at).days} 天"
                    retest_due += 1
                elif due_at <= now + dt.timedelta(days=RETEST_SOON_DAYS):
                    window = f"复测窗口 {(due_at - now).days + 1} 天内"
                    retest_due += 1
                else:
                    window = f"复测约定 {due_at:%m-%d}"
            delta = teaching_service.mastery_delta(record.id, record.user_id)
            interventions_out.append(
                {
                    "id": record.id,
                    "student": usernames.get(record.user_id, f"#{record.user_id}"),
                    "knowledge_point": record.knowledge_point,
                    "strategy": record.strategy,
                    "outcome": record.outcome,
                    "window": window,
                    "question_ids": list(record.question_ids or []),
                    "mastery": delta,
                }
            )

        # 最近动态：录入 + 复习合并时间线
        qids = {log.question_id for log in recent_logs}
        log_snippets: dict[int, str] = {}
        if qids:
            with self._session() as session:
                for q in session.execute(
                    select(Question).where(Question.id.in_(qids))
                ).scalars():
                    log_snippets[q.id] = q.content_markdown
        feed: list[dict] = []
        for q in recent_questions:
            feed.append(
                {
                    "kind": "录入",
                    "at": q.created_at,
                    "username": usernames.get(q.user_id, f"#{q.user_id}"),
                    "text": (q.content_markdown or "")[:44],
                }
            )
        for log in recent_logs:
            feed.append(
                {
                    "kind": "复习",
                    "at": log.reviewed_at,
                    "username": usernames.get(log.user_id, f"#{log.user_id}"),
                    "text": f"{_GRADE_LABELS.get(log.grade, log.grade)} · "
                    + (log_snippets.get(log.question_id, "") or "")[:36],
                }
            )
        feed.sort(key=lambda x: x["at"] or dt.datetime.min.replace(tzinfo=dt.timezone.utc), reverse=True)
        feed = feed[:12]

        totals = {
            "students": len(rows),
            "due": sum(due_map.values()),
            "overdue": sum(overdue_map.values()),
            "retest_due": retest_due,
            "in_progress": len(interventions_out),
        }
        result.update(
            students=rows,
            totals=totals,
            interventions=interventions_out,
            activity=feed,
        )
        logger.info(
            "教师工作台聚合完成 teacher=%s students=%s due=%s overdue=%s retest_due=%s",
            teacher_id,
            totals["students"],
            totals["due"],
            totals["overdue"],
            totals["retest_due"],
        )
        return result
