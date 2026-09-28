"""知识点掌握度引擎（Batch 04/05）。

职责：
1. 关联同步：题目上的知识点名称（JSON 列）→ 规范化 knowledge_points / question_knowledge_points；
2. 掌握度计算：基于复习日志按时间加权，输出每个知识点 0~1 的掌握度画像；
3. 今日计划：SM-2 到期优先 + 薄弱知识点加固的自适应复习队列。

掌握度模型（对单题）：
    score(grade) = again 0.0 / hard 0.6 / good 0.85 / easy 1.0
    按复习时间从旧到新给指数衰减权重（最新一次权重 1.0，衰减系数 DECAY），
    加权平均即该题掌握度；从未复习过的题按 UNREVIEWED_SCORE 计。
知识点掌握度 = 关联题目掌握度的均值。
"""
from __future__ import annotations

import datetime as dt
from collections import defaultdict
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session, sessionmaker

from backend.models.orm import KnowledgePoint, Question, QuestionKnowledgePoint, ReviewLog
from backend.models.schemas import QuestionOut
from backend.utils.logging import get_logger

logger = get_logger(__name__)

SCORE_BY_GRADE: dict[str, float] = {
    "again": 0.0,
    "hard": 0.6,
    "good": 0.85,
    "easy": 1.0,
}
DECAY = 0.65  # 每往前一次复习，权重乘以 DECAY
UNREVIEWED_SCORE = 0.2
WEAK_THRESHOLD = 0.4
SHAKY_THRESHOLD = 0.7

STATUS_LABEL = {"weak": "薄弱", "shaky": "不稳固", "solid": "已掌握"}


def mastery_status(mastery: float) -> str:
    if mastery < WEAK_THRESHOLD:
        return "weak"
    if mastery < SHAKY_THRESHOLD:
        return "shaky"
    return "solid"


def question_mastery(logs: list[ReviewLog]) -> float:
    """单题掌握度：时间加权平均（logs 按时间任意序，内部排序）。"""
    if not logs:
        return UNREVIEWED_SCORE
    epoch = dt.datetime.min.replace(tzinfo=dt.timezone.utc)
    ordered = sorted(logs, key=lambda log: log.reviewed_at or epoch)
    weighted_sum = 0.0
    weight_total = 0.0
    for index, log in enumerate(ordered):
        weight = DECAY ** (len(ordered) - 1 - index)
        weighted_sum += SCORE_BY_GRADE.get(log.grade, 0.0) * weight
        weight_total += weight
    return weighted_sum / weight_total if weight_total else UNREVIEWED_SCORE


def sync_question_links(session: Session, question_id: int, names: list[str]) -> None:
    """把题目的知识点名称同步到 M2M 关联（get-or-create，幂等）。

    必须在调用方事务内执行；空名称自动过滤，重复名称去重。
    """
    clean: list[str] = []
    for name in names or []:
        stripped = (name or "").strip()
        if stripped and stripped not in clean:
            clean.append(stripped)

    session.execute(
        delete(QuestionKnowledgePoint).where(QuestionKnowledgePoint.question_id == question_id)
    )
    for name in clean:
        kp = session.execute(
            select(KnowledgePoint).where(KnowledgePoint.name == name)
        ).scalar_one_or_none()
        if kp is None:
            kp = KnowledgePoint(name=name)
            session.add(kp)
            session.flush()
        session.add(QuestionKnowledgePoint(question_id=question_id, knowledge_point_id=kp.id))


@dataclass
class KPMastery:
    """一个知识点的掌握度画像条目。"""

    knowledge_point: str
    mastery: float
    question_count: int
    due_count: int

    @property
    def status(self) -> str:
        return mastery_status(self.mastery)

    @property
    def status_label(self) -> str:
        return STATUS_LABEL[self.status]


@dataclass
class PlanItem:
    """今日复习计划条目：题目 + 推荐理由 + 优先级（大者优先）。"""

    question: QuestionOut
    reason: str
    priority: float


class MasteryEngine:
    """掌握度画像与自适应复习计划的领域服务。"""

    def __init__(
        self,
        session_factory: sessionmaker | Callable[[], Iterator[Session]] | None = None,
    ):
        self._session_factory = session_factory

    @contextmanager
    def _session(self) -> Iterator[Session]:
        if self._session_factory is None:
            from backend.database import SessionLocal

            factory: sessionmaker = SessionLocal
        else:
            factory = self._session_factory  # type: ignore[assignment]
        session = factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def _ensure_links(self, session: Session, user_id: int) -> None:
        """老数据自愈：旧版题目知识点只存在 JSON 列、M2M 为空时补建关联（一次性）。"""
        linked = session.execute(
            select(func.count())
            .select_from(QuestionKnowledgePoint)
            .join(Question, Question.id == QuestionKnowledgePoint.question_id)
            .where(Question.user_id == user_id)
        ).scalar_one()
        if linked:
            return
        for question in session.execute(
            select(Question).where(Question.user_id == user_id)
        ).scalars():
            points = list(question.knowledge_points or [])
            if points:
                sync_question_links(session, question.id, points)
        logger.info("已为 user=%s 补建知识点 M2M 关联（老数据回填）", user_id)

    def _compute_profile(self, session: Session, user_id: int) -> list[KPMastery]:
        self._ensure_links(session, user_id)
        links = session.execute(
            select(QuestionKnowledgePoint, Question)
            .join(Question, Question.id == QuestionKnowledgePoint.question_id)
            .where(Question.user_id == user_id)
        ).all()
        if not links:
            return []

        question_ids = list({qkp.question_id for qkp, _ in links})
        kp_ids = list({qkp.knowledge_point_id for qkp, _ in links})
        kp_names = {
            kp.id: kp.name
            for kp in session.execute(
                select(KnowledgePoint).where(KnowledgePoint.id.in_(kp_ids))
            ).scalars()
        }
        logs_by_question: dict[int, list[ReviewLog]] = defaultdict(list)
        for log in session.execute(
            select(ReviewLog).where(
                ReviewLog.user_id == user_id,
                ReviewLog.question_id.in_(question_ids),
            )
        ).scalars():
            logs_by_question[log.question_id].append(log)

        now = dt.datetime.now(dt.timezone.utc)
        scores_per_kp: dict[int, list[float]] = defaultdict(list)
        due_per_kp: dict[int, int] = defaultdict(int)
        count_per_kp: dict[int, int] = defaultdict(int)
        for qkp, question in links:
            scores_per_kp[qkp.knowledge_point_id].append(
                question_mastery(logs_by_question.get(question.id, []))
            )
            count_per_kp[qkp.knowledge_point_id] += 1
            due = question.due_at
            if due is not None and due.tzinfo is None:
                due = due.replace(tzinfo=dt.timezone.utc)
            if due is None or due <= now:
                due_per_kp[qkp.knowledge_point_id] += 1

        items = [
            KPMastery(
                knowledge_point=kp_names.get(kp_id, f"kp#{kp_id}"),
                mastery=sum(scores) / len(scores),
                question_count=count_per_kp[kp_id],
                due_count=due_per_kp.get(kp_id, 0),
            )
            for kp_id, scores in scores_per_kp.items()
        ]
        items.sort(key=lambda item: item.mastery)
        return items

    def profile(self, user_id: int, limit: int | None = None) -> list[KPMastery]:
        """用户全部知识点的掌握度画像，薄弱者排前。"""
        with self._session() as session:
            items = self._compute_profile(session, user_id)
        return items[:limit] if limit else items

    def today_plan(self, user_id: int, size: int = 10) -> list[PlanItem]:
        """自适应复习计划：SM-2 到期题优先，其余名额由薄弱知识点加固补齐。

        已掌握归档的题目（reps>=3 且 interval>=21 天）不进入计划。
        """
        size = max(0, size)
        if size == 0:
            return []
        now = dt.datetime.now(dt.timezone.utc)

        with self._session() as session:
            profile = self._compute_profile(session, user_id)
            weak = [item for item in profile if item.mastery < SHAKY_THRESHOLD]
            mastery_by_name = {item.knowledge_point: item.mastery for item in weak}

            plan: list[PlanItem] = []
            picked: set[int] = set()

            due_rows = (
                session.execute(
                    select(Question)
                    .where(
                        Question.user_id == user_id,
                        or_(Question.due_at.is_(None), Question.due_at <= now),
                    )
                    .order_by(Question.due_at.asc().nulls_first())
                    .limit(size)
                )
                .scalars()
                .all()
            )
            for question in due_rows:
                if len(plan) >= size:
                    break
                out = QuestionOut.from_orm_model(question)
                if out.mastered:
                    continue
                overdue_days = 0.0
                if question.due_at is not None:
                    due = (
                        question.due_at
                        if question.due_at.tzinfo
                        else question.due_at.replace(tzinfo=dt.timezone.utc)
                    )
                    overdue_days = max(0.0, (now - due).total_seconds() / 86400)
                plan.append(
                    PlanItem(
                        question=out,
                        reason="到期复习" if overdue_days < 1 else f"已逾期 {overdue_days:.0f} 天",
                        priority=10.0 + overdue_days,
                    )
                )
                picked.add(question.id)

            remaining = size - len(plan)
            if remaining <= 0 or not mastery_by_name:
                return plan

            weak_names = list(mastery_by_name)
            candidates = (
                session.execute(
                    select(Question)
                    .join(
                        QuestionKnowledgePoint,
                        QuestionKnowledgePoint.question_id == Question.id,
                    )
                    .join(
                        KnowledgePoint,
                        KnowledgePoint.id == QuestionKnowledgePoint.knowledge_point_id,
                    )
                    .where(Question.user_id == user_id, KnowledgePoint.name.in_(weak_names))
                    .order_by(Question.due_at.asc().nulls_first())
                    .limit(remaining * 3)
                )
                .scalars()
                .all()
            )
            candidate_ids = [q.id for q in candidates]
            names_by_qid: dict[int, list[str]] = defaultdict(list)
            if candidate_ids:
                for qid, name in session.execute(
                    select(QuestionKnowledgePoint.question_id, KnowledgePoint.name)
                    .join(
                        KnowledgePoint,
                        KnowledgePoint.id == QuestionKnowledgePoint.knowledge_point_id,
                    )
                    .where(QuestionKnowledgePoint.question_id.in_(candidate_ids))
                ).all():
                    names_by_qid[qid].append(name)

            for question in candidates:
                if len(plan) >= size:
                    break
                if question.id in picked:
                    continue
                out = QuestionOut.from_orm_model(question)
                if out.mastered:
                    continue
                weak_linked = [n for n in names_by_qid.get(question.id, []) if n in mastery_by_name]
                weakest = min(weak_linked, key=lambda n: mastery_by_name[n]) if weak_linked else ""
                mastery = mastery_by_name.get(weakest, 0.0)
                plan.append(
                    PlanItem(
                        question=out,
                        reason=f"薄弱知识点：{weakest}（掌握度 {mastery:.0%}）",
                        priority=5.0 + (SHAKY_THRESHOLD - mastery),
                    )
                )
                picked.add(question.id)
            return plan
