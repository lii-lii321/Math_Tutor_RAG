"""错题仓储：错题 CRUD、筛选、复习调度状态读写。

返回 ORM 实例供服务层加工，界面层只接触 QuestionOut 契约。
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import String, delete, func, or_, select
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
        ocr_text: str | None = None,
        image_hash: str | None = None,
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
            ocr_text=ocr_text or None,
            image_hash=image_hash,
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
        user_note: str | None = None,
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
        if user_note is not None:
            question.user_note = user_note
        self.session.flush()
        return question

    def add_tags(
        self, question_ids: list[int], user_id: int, new_tags: list[str]
    ) -> int:
        """为一组错题合并追加标签（去重），返回处理数量。"""
        changed = 0
        for qid in question_ids:
            question = self._get_owned(qid, user_id)
            if question is None:
                continue
            merged = list(question.tags or [])
            for tag in new_tags:
                if tag and tag not in merged:
                    merged.append(tag)
            if merged != (question.tags or []):
                question.tags = merged
            changed += 1
        self.session.flush()
        return changed

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

    def find_by_image_hash(self, user_id: int, image_hash: str) -> Question | None:
        """按原图哈希查找用户的既有错题（上传去重用）。"""
        return self.session.execute(
            select(Question)
            .where(Question.user_id == user_id, Question.image_hash == image_hash)
            .order_by(Question.created_at.desc())
        ).scalars().first()

    def get_by_ids(self, ids: list[int]) -> list[Question]:
        """按 id 批量获取（不做归属过滤，调用方负责鉴权）。"""
        if not ids:
            return []
        return list(
            self.session.execute(
                select(Question).where(Question.id.in_(ids))
            ).scalars()
        )

    def _filtered_stmt(
        self,
        user_id: int,
        *,
        include_others: bool = False,
        tag: str | None = None,
        keyword: str | None = None,
    ):
        """构造带归属/标签/关键词过滤的查询（过滤全部下推到 SQL）。

        tags / knowledge_points 为 JSON 列，SQLite 与 MySQL 均以文本存储，
        用 LIKE 匹配带引号的标签即可精确命中。
        """
        stmt = select(Question).order_by(Question.created_at.desc())
        if not include_others:
            stmt = stmt.where(Question.user_id == user_id)
        if tag:
            stmt = stmt.where(Question.tags.cast(String).contains(f'"{tag}"'))
        if keyword:
            like = f"%{keyword}%"
            stmt = stmt.where(
                or_(
                    Question.content_markdown.ilike(like),
                    Question.answer.ilike(like),
                    Question.ocr_text.ilike(like),
                    Question.tags.cast(String).ilike(like),
                    Question.knowledge_points.cast(String).ilike(like),
                )
            )
        return stmt

    def list_for_user(
        self,
        user_id: int,
        *,
        include_others: bool = False,
        tag: str | None = None,
        keyword: str | None = None,
        offset: int = 0,
        limit: int | None = None,
    ) -> list[Question]:
        stmt = self._filtered_stmt(
            user_id, include_others=include_others, tag=tag, keyword=keyword
        )
        if offset:
            stmt = stmt.offset(offset)
        if limit is not None:
            stmt = stmt.limit(limit)
        return list(self.session.execute(stmt).scalars())

    def count_for_user(
        self,
        user_id: int,
        *,
        include_others: bool = False,
        tag: str | None = None,
        keyword: str | None = None,
    ) -> int:
        """与 list_for_user 相同口径的总数（供分页使用，SQL 计数）。"""
        stmt = self._filtered_stmt(
            user_id, include_others=include_others, tag=tag, keyword=keyword
        )
        count_stmt = select(func.count()).select_from(stmt.subquery())
        return int(self.session.execute(count_stmt).scalar_one())

    def due_for_review(self, user_id: int, now: dt.datetime | None = None) -> list[Question]:
        """到期错题（SQL 下推）；新题 due_at 为 NULL 视为立即到期。"""
        now = now or dt.datetime.now(dt.timezone.utc)
        stmt = (
            select(Question)
            .where(Question.user_id == user_id)
            .where(or_(Question.due_at.is_(None), Question.due_at <= now))
            .order_by(Question.created_at.desc())
        )
        return list(self.session.execute(stmt).scalars())

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

    def all_review_logs(self) -> list[ReviewLog]:
        """全部用户的复习记录（教师报表用）。"""
        stmt = select(ReviewLog).order_by(ReviewLog.reviewed_at.asc())
        return list(self.session.execute(stmt).scalars())

    # ---------- 内部 ----------
    def _get_owned(self, question_id: int, user_id: int) -> Question | None:
        return self.session.execute(
            select(Question).where(Question.id == question_id, Question.user_id == user_id)
        ).scalar_one_or_none()


def to_out(question: Question) -> QuestionOut:
    return QuestionOut.from_orm_model(question)
