"""教学闭环服务（MVP）：诊断薄弱点 → 干预练习 → 独立作答 → 延迟复测 → 归档。

设计要点：
- teaching_interventions 表是唯一事实源，状态机
  diagnosed → practiced → retest_scheduled → retest_passed / retest_failed；
- 「单次答对 ≠ 掌握」：独立作答通过后约定延迟复测（默认 7 天），
  复测通过才把题目的 retest_verified_at 落地——它是 mastered 归档
  门槛（SM-2 达标 + 复测确认）的一半；
- 全部操作按 user_id 归属校验，跨用户访问按业务错误拒绝。
"""
from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Iterator
from contextlib import contextmanager

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from backend.models.orm import Question, ReviewLog, TeachingIntervention
from backend.utils.logging import get_logger

logger = get_logger(__name__)

RETEST_DELAY_DAYS = 7

OUTCOME_DIAGNOSED = "diagnosed"
OUTCOME_PRACTICED = "practiced"
OUTCOME_RETEST_SCHEDULED = "retest_scheduled"
OUTCOME_RETEST_PASSED = "retest_passed"
OUTCOME_RETEST_FAILED = "retest_failed"

# 教学策略启发式：与 mastery.py 的 WEAK/SHAKY 阈值同源
STRATEGY_BY_STATUS = {
    "weak": ("weak_drill", "概念重建 + 基础变式逐级过关"),
    "shaky": ("error_cause", "错因归类 + 针对性变式练习"),
    "solid": ("maintenance", "保温：低频综合卷维持手感"),
}


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class TeachingService:
    """教学干预闭环：诊断、练习登记、作答结果、延迟复测。"""

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

    @staticmethod
    def _get_owned(
        session: Session, intervention_id: int, user_id: int
    ) -> TeachingIntervention | None:
        return session.execute(
            select(TeachingIntervention).where(
                TeachingIntervention.id == intervention_id,
                TeachingIntervention.user_id == user_id,
            )
        ).scalar_one_or_none()

    # ---------- ① 诊断 ----------

    def start_intervention(self, user_id: int, knowledge_point: str) -> dict:
        """诊断一个知识点：掌握度 + 关联错题清单 + 教学策略，落一条干预记录。"""
        kp = (knowledge_point or "").strip()
        if not kp:
            raise ValueError("知识点名称不能为空")

        from backend.repositories.questions import QuestionRepository
        from backend.services.mastery import MasteryEngine, mastery_status

        mastery_engine = MasteryEngine(self._session_factory)
        profile = next(
            (item for item in mastery_engine.profile(user_id) if item.knowledge_point == kp),
            None,
        )
        if profile is None:
            raise ValueError(f"画像中不存在知识点「{kp}」——先录几道相关错题再开始干预")

        with self._session() as session:
            questions = QuestionRepository(session).list_for_user(
                user_id, knowledge_point=kp
            )
            question_ids = [q.id for q in questions]
            status = mastery_status(profile.mastery)
            strategy, strategy_note = STRATEGY_BY_STATUS.get(
                status, ("maintenance", "保温：低频综合卷维持手感")
            )
            record = TeachingIntervention(
                user_id=user_id,
                knowledge_point=kp,
                strategy=strategy,
                question_ids=question_ids,
                outcome=OUTCOME_DIAGNOSED,
                note=profile.status_label,
            )
            session.add(record)
            session.flush()
            return {
                "intervention_id": record.id,
                "knowledge_point": kp,
                "mastery": round(profile.mastery, 3),
                "status": status,
                "status_label": profile.status_label,
                "question_count": len(question_ids),
                "question_ids": question_ids,
                "strategy": strategy,
                "strategy_note": strategy_note,
                "due_count": profile.due_count,
            }

    # ---------- ② 练习登记 ----------

    def record_practice(
        self,
        intervention_id: int,
        user_id: int,
        question_ids: list[int] | None = None,
        *,
        variant_source_id: int | None = None,
    ) -> dict:
        """登记实际练习的题目（可与诊断清单不同：教师按情现场选题/加变式）。"""
        with self._session() as session:
            record = self._get_owned(session, intervention_id, user_id)
            if record is None:
                raise ValueError("干预记录不存在或无权访问")
            if record.outcome not in (OUTCOME_DIAGNOSED, OUTCOME_PRACTICED):
                raise ValueError(f"当前状态 {record.outcome} 不允许登记练习")
            if question_ids:
                record.question_ids = [int(q) for q in question_ids]
            if variant_source_id is not None:
                record.variant_source_id = int(variant_source_id)
            record.outcome = OUTCOME_PRACTICED
            session.flush()
            return self._to_dict(record)

    # ---------- ③ 独立作答结果 ----------

    def record_outcome(
        self, intervention_id: int, user_id: int, passed: bool, note: str = ""
    ) -> dict:
        """登记独立作答结果：通过 → 约定延迟复测；未通过 → 留在 practiced 待再练。"""
        with self._session() as session:
            record = self._get_owned(session, intervention_id, user_id)
            if record is None:
                raise ValueError("干预记录不存在或无权访问")
            if record.outcome != OUTCOME_PRACTICED:
                raise ValueError(f"当前状态 {record.outcome} 不允许登记作答结果")
            if passed:
                record.outcome = OUTCOME_RETEST_SCHEDULED
                record.retest_due_at = _now() + dt.timedelta(days=RETEST_DELAY_DAYS)
            else:
                # 未通过：保持 practiced，可再来一轮练习
                record.note = (note or "独立作答未通过，待再练").strip() or None
            session.flush()
            return self._to_dict(record)

    # ---------- ④ 延迟复测 ----------

    def record_retest(
        self,
        intervention_id: int,
        user_id: int,
        passed: bool,
        question_id: int,
        *,
        note: str = "",
    ) -> dict:
        """登记延迟复测结果。

        通过 → 关联题目落 retest_verified_at（mastered 门槛的复测半边）；
        未通过 → 干预标记 retest_failed，题目留复习池。
        """
        with self._session() as session:
            record = self._get_owned(session, intervention_id, user_id)
            if record is None:
                raise ValueError("干预记录不存在或无权访问")
            if record.outcome != OUTCOME_RETEST_SCHEDULED:
                raise ValueError(
                    f"当前状态 {record.outcome} 不允许登记复测（需先约定复测时间）"
                )
            question = session.execute(
                select(Question).where(
                    Question.id == int(question_id), Question.user_id == user_id
                )
            ).scalar_one_or_none()
            if question is None:
                raise ValueError("复测题目不存在或不属于当前用户")
            now = _now()
            if passed:
                record.outcome = OUTCOME_RETEST_PASSED
                question.retest_verified_at = now
            else:
                record.outcome = OUTCOME_RETEST_FAILED
            if note:
                record.note = note.strip()
            session.flush()
            logger.info(
                "教学复测登记 intervention=%s user=%s passed=%s question=%s",
                intervention_id,
                user_id,
                passed,
                question_id,
            )
            return self._to_dict(record)

    # ---------- 查询 ----------

    def mastery_delta(self, intervention_id: int, user_id: int) -> dict | None:
        """干预有效性对比：诊断时点掌握度 → 当前掌握度（回答「有没有用」）。

        按干预覆盖题目逐题计算（无日志题按 UNREVIEWED_SCORE 计，与掌握度
        引擎口径一致）；before 只用诊断时间戳之前的复习日志。
        """
        from collections import defaultdict

        from backend.services.mastery import UNREVIEWED_SCORE, question_mastery

        with self._session() as session:
            record = self._get_owned(session, intervention_id, user_id)
            if record is None:
                return None
            qids = [int(q) for q in (record.question_ids or []) if str(q).isdigit()]
            created = record.created_at or _now()
            if created.tzinfo is None:
                created = created.replace(tzinfo=dt.timezone.utc)
            logs = (
                session.execute(
                    select(ReviewLog).where(
                        ReviewLog.user_id == user_id,
                        ReviewLog.question_id.in_(qids),
                    )
                )
                .scalars()
                .all()
                if qids
                else []
            )
        if not qids:
            return None

        epoch = dt.datetime.min.replace(tzinfo=dt.timezone.utc)

        def _aware(value: dt.datetime | None) -> dt.datetime:
            if value is None:
                return epoch
            return value if value.tzinfo else value.replace(tzinfo=dt.timezone.utc)

        aware_created = _aware(created)
        before_logs = [l for l in logs if _aware(l.reviewed_at) <= aware_created]

        def _kp_mastery(logs: list) -> float:
            per_question: dict[int, list] = defaultdict(list)
            for log in logs:
                per_question[log.question_id].append(log)
            values = [
                question_mastery(per_question.get(qid, [])) for qid in qids
            ]
            return sum(values) / len(values)

        before = _kp_mastery(before_logs)
        after = _kp_mastery(list(logs))
        return {
            "before": round(before, 3),
            "after": round(after, 3),
            "delta": round(after - before, 3),
            "reviewed_after": sum(1 for l in logs if _aware(l.reviewed_at) > aware_created),
        }

    def history(self, user_id: int, limit: int = 20) -> list[dict]:
        """干预历史（新→旧），供 Agent/教师查看教学档案。"""
        with self._session() as session:
            rows = (
                session.execute(
                    select(TeachingIntervention)
                    .where(TeachingIntervention.user_id == user_id)
                    .order_by(TeachingIntervention.created_at.desc())
                    .limit(min(int(limit), 100))
                )
                .scalars()
                .all()
            )
            return [self._to_dict(row) for row in rows]

    @staticmethod
    def _to_dict(record: TeachingIntervention) -> dict:
        return {
            "id": record.id,
            "knowledge_point": record.knowledge_point,
            "strategy": record.strategy,
            "question_ids": list(record.question_ids or []),
            "variant_source_id": record.variant_source_id,
            "outcome": record.outcome,
            "note": record.note,
            "retest_due_at": record.retest_due_at.isoformat()
            if record.retest_due_at
            else None,
            "created_at": record.created_at.isoformat() if record.created_at else None,
        }
