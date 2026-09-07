"""错题仓储：错题 CRUD、筛选、复习调度状态读写。

返回 ORM 实例供服务层加工，界面层只接触 QuestionOut 契约。
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from backend.models.orm import Question, ReviewLog
from backend.models.schemas import QuestionOut


class QuestionRepository:
    def __init__(self, session: Session):
        self.session = session

    # ---------- 写入 ----------
    def create(
        self,
        user_id: int,
        *,
        content_markdown: str,
        answer: str = "",
        knowledge_points: list[str] | None = None,
        tags: list[str] | None = None,
        difficulty: str = "medium",
        followup_question: str = "",
        image_path: str | None = None,
        source: str = "ai",
    ) -> Question:
        question = Question(
            user_id=user_id,
            content_markdown=content_markdown,
            answer=answer,
            knowledge_points=knowledge_points or [],
            tags=tags or [],
            difficulty=difficulty,
            followup_question=followup_question or None,
            image_path=image_path,
            source=source,
        )
        self.session.add(question)
        self.session.flush()
        return question

    def update(
        self,
        question_id: int,
        user_id: int,
        *,
        content_markdown: str | None = None,
        answer: str | None = None,
        tags: list[str] | None = None,
        knowledge_points: list[str] | None = None,
    ) -> Question | None:
        question = self._get_owned(question_id, user_id)
        if question is None:
            return None
        if content_markdown is not None:
            question.content_markdown = content_markdown
        if answer is not None:
            question.answer = answer
        if tags is not None:
            question.tags = tags
        if knowledge_points is not None:
            question.knowledge_points = knowledge_points
        self.session.flush()
        return question

    def delete_many(self, question_ids: list[int], user_id: int) -> int:
        if not question_ids:
            return 0
        result = self.session.execute(
            delete(Question).where(
                Question.id.in_(question_ids), Question.user_id == user_id
            )
        )
        return int(result.rowcount or 0)

    # ---------- 查询 ----------
    def get_owned(self, question_id: int, user_id: int) -> Question | None:
        return self._get_owned(question_id, user_id)

    def list_for_user(
        self,
        user_id: int,
        *,
        include_others: bool = False,
        tag: str | None = None,
        keyword: str | None = None,
        limit: int = 500,
    ) -> list[Question]:
        stmt = select(Question).order_by(Question.created_at.desc()).limit(limit)
        if not include_others:
            stmt = stmt.where(Question.user_id == user_id)
        questions = list(self.session.execute(stmt).scalars())

        if tag:
            questions = [q for q in questions if tag in (q.tags or [])]
        if keyword:
            kw = keyword.lower()
            questions = [
                q
                for q in questions
                if kw in (q.content_markdown or "").lower()
                or kw in (q.answer or "").lower()
                or any(kw in str(t).lower() for t in (q.tags or []))
                or any(kw in str(t).lower() for t in (q.knowledge_points or []))
            ]
        return questions

    def due_for_review(self, user_id: int, now: dt.datetime | None = None) -> list[Question]:
        questions = self.list_for_user(user_id)
        return [q for q in questions if q.is_due(now)]

    def count_by_tag(self, questions: list[Question]) -> dict[str, int]:
        counter: dict[str, int] = {}
        for question in questions:
            for tag in question.tags or []:
                counter[tag] = counter.get(tag, 0) + 1
        return dict(sorted(counter.items(), key=lambda kv: kv[1], reverse=True))

    # ---------- 复习调度 ----------
    def apply_schedule(
        self,
        question_id: int,
        user_id: int,
        *,
        grade: str,
        quality: int,
        prev_interval: float,
        next_interval: float,
        ease_after: float,
        due_at: dt.datetime,
    ) -> Question | None:
        question = self._get_owned(question_id, user_id)
        if question is None:
            return None
        question.reps = question.reps + 1 if quality >= 3 else 0
        question.ease = ease_after
        question.interval_days = next_interval
        question.due_at = due_at
        question.last_reviewed_at = dt.datetime.now(dt.timezone.utc)
        self.session.add(
            ReviewLog(
                question_id=question.id,
                user_id=user_id,
                grade=grade,
                quality=quality,
                prev_interval=prev_interval,
                next_interval=next_interval,
                ease_after=ease_after,
            )
        )
        self.session.flush()
        return question

    def review_logs_for_user(self, user_id: int) -> list[ReviewLog]:
        stmt = (
            select(ReviewLog)
            .where(ReviewLog.user_id == user_id)
            .order_by(ReviewLog.reviewed_at.asc())
        )
        return list(self.session.execute(stmt).scalars())

    # ---------- 内部 ----------
    def _get_owned(self, question_id: int, user_id: int) -> Question | None:
        return self.session.execute(
            select(Question).where(Question.id == question_id, Question.user_id == user_id)
        ).scalar_one_or_none()


def to_out(question: Question) -> QuestionOut:
    return QuestionOut.from_orm_model(question)
