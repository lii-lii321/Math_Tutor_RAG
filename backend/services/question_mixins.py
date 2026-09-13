"""QuestionService 的 Mixin 拆分：按领域分组的方法集合。

QuestionService 由这些 Mixin 组合而成（见 question_service.py），
公共 API 与拆分前完全一致。CoreMixin 提供共享基础设施。
"""
from __future__ import annotations

import datetime as dt
import io
import re
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING

from backend.config import get_settings
from backend.models.schemas import QuestionAnalysis, QuestionOut, TagStat
from backend.repositories.questions import QuestionRepository
from backend.services.ai import get_ai_service
from backend.services.ai.base import BaseAIProvider
from backend.services.rag import QuestionVectorStore
from backend.services.review import ReviewScheduler
from backend.services.stats import (
    build_accuracy_trend,
    build_activity,
    build_calendar,
    build_tag_stats,
    mastery_trend,
    study_streak,
    weak_tags,
    weekly_report,
)
from backend.utils.logging import get_logger

if TYPE_CHECKING:  # pragma: no cover
    from sqlalchemy.orm import Session, sessionmaker

logger = get_logger("questions")


def _aware(value: dt.datetime) -> dt.datetime:
    return value if value.tzinfo else value.replace(tzinfo=dt.timezone.utc)


def sanitize_tags(raw: str) -> list[str]:
    """把用户手填的逗号/中文逗号分隔标签串规整为列表。"""
    parts = re.split(r"[,，;；]", raw or "")
    seen: list[str] = []
    for part in parts:
        tag = part.strip()
        if tag and tag not in seen:
            seen.append(tag)
    return seen


class CoreMixin:
    """共享基础设施：配置、会话、AI 客户端、向量库、图片落盘、索引。"""

    settings: object
    ai: BaseAIProvider
    vector_store: QuestionVectorStore
    scheduler: ReviewScheduler

    def __init__(
        self,
        session_factory: sessionmaker | Callable[[], Iterator[Session]] | None = None,
    ):
        self.settings = get_settings()
        self._session_factory = session_factory
        self.ai: BaseAIProvider = get_ai_service(self.settings)
        self.vector_store = QuestionVectorStore(self.settings)
        self.scheduler = ReviewScheduler(self.settings)

    @contextmanager
    def _session(self) -> Iterator[QuestionRepository]:
        if self._session_factory is None:
            from backend.database import SessionLocal

            factory = SessionLocal
        else:
            factory = self._session_factory
        session = factory()
        try:
            yield QuestionRepository(session)
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    @contextmanager
    def _user_session(self) -> Iterator[object]:
        from backend.repositories.users import UserRepository

        if self._session_factory is None:
            from backend.database import SessionLocal

            factory = SessionLocal
        else:
            factory = self._session_factory
        session = factory()
        try:
            yield UserRepository(session)
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def _search_scope(self, user_id: int, include_others: bool) -> list[int]:
        """语义检索的可见范围：普通用户仅自己；教师为 自己 + 全部学生。"""
        if not include_others:
            return [user_id]
        with self._user_session() as users:
            return [
                u.id
                for u in users.list_users()
                if u.role == "student" or u.id == user_id
            ]

    def _persist_image(self, user_id: int, image_bytes: bytes) -> Path:
        """图片落盘：压缩到最长边 1600px 的 JPEG，节省存储并加快导出。"""
        user_dir = self.settings.data_dir / "images" / f"u{user_id}"
        user_dir.mkdir(parents=True, exist_ok=True)
        path = user_dir / f"{dt.datetime.now():%Y%m%d_%H%M%S}_{uuid.uuid4().hex[:8]}.jpg"
        try:
            from PIL import Image

            with Image.open(io.BytesIO(image_bytes)) as image:
                image = image.convert("RGB")
                if max(image.size) > 1600:
                    image.thumbnail((1600, 1600))
                image.save(path, "JPEG", quality=85, optimize=True)
        except Exception as exc:  # noqa: BLE001 - 非 JPEG/损坏图片回退为原样保存
            logger.warning("图片压缩失败，按原样保存: %s", exc)
            path.write_bytes(image_bytes)
        return path

    @staticmethod
    def _embeddable_text(analysis: QuestionAnalysis) -> str:
        return " ".join(
            [
                " ".join(analysis.knowledge_points),
                analysis.analysis,
                analysis.answer,
                analysis.mistake_cause,
                " ".join(analysis.tags),
            ]
        )

    def _reindex_owned(self, question) -> None:  # noqa: ANN001 - ORM 实例
        out = QuestionOut.from_orm_model(question)
        self.vector_store.upsert_question(
            out.id,
            " ".join(
                [*(out.knowledge_points or []), out.content_markdown, out.answer or ""]
            ),
            user_id=out.user_id,
            tags=out.tags,
        )


class EntryMixin:
    """错题录入：手动文本与拍照 AI 解析两条链路。"""

    def create_manual_question(
        self,
        user_id: int,
        *,
        content_markdown: str,
        answer: str = "",
        tags: list[str] | None = None,
        knowledge_points: list[str] | None = None,
        source: str = "manual",
        ai_analyze: bool = False,
        hint: str = "",
    ) -> QuestionOut:
        """手动录入文本错题：入库 + 向量索引；可选 AI 文本解析补全空缺标注。"""
        if not content_markdown or not content_markdown.strip():
            raise ValueError("题目内容不能为空")
        clean_tags = [t.strip() for t in (tags or []) if t.strip()]
        clean_points = [t.strip() for t in (knowledge_points or []) if t.strip()]
        clean_answer = (answer or "").strip()
        followup = ""

        if ai_analyze:
            analysis = self.ai.analyze_text(content_markdown.strip(), hint)
            clean_answer = clean_answer or analysis.answer
            clean_points = clean_points or analysis.knowledge_points[:4]
            clean_tags = clean_tags or analysis.tags[:4]
            followup = analysis.followup_question

        with self._session() as repo:
            question = repo.create(
                user_id,
                content_markdown=content_markdown.strip(),
                answer=clean_answer,
                knowledge_points=clean_points,
                tags=clean_tags,
                followup_question=followup,
                source=source,
            )
            out = QuestionOut.from_orm_model(question)

        self.vector_store.upsert_question(
            out.id,
            " ".join([*clean_points, content_markdown.strip(), clean_answer, *clean_tags]),
            user_id=user_id,
            tags=clean_tags,
        )
        return out

    def analyze_and_save(
        self,
        user_id: int,
        image_bytes: bytes,
        *,
        mime_type: str = "image/jpeg",
        user_tags: list[str] | None = None,
        hint: str = "",
    ) -> tuple[QuestionOut, QuestionAnalysis]:
        """完整录入链路：AI 解析 → 图片落盘 →（可选 OCR）→ 数据库 → 向量索引。"""
        analysis = self.ai.analyze_question(image_bytes, mime_type, hint)
        tags = analysis.merged_tags(user_tags or [])

        image_path = self._persist_image(user_id, image_bytes)
        from backend.services.ocr import extract_text

        ocr_text = extract_text(str(image_path))
        with self._session() as repo:
            question = repo.create(
                user_id,
                content_markdown=analysis.analysis,
                answer=analysis.answer,
                knowledge_points=analysis.knowledge_points,
                tags=tags,
                difficulty=analysis.difficulty,
                followup_question=analysis.followup_question,
                image_path=str(image_path),
                ocr_text=ocr_text,
            )
            out = QuestionOut.from_orm_model(question)

        embed_text = self._embeddable_text(analysis)
        if ocr_text:
            embed_text = f"{embed_text} {ocr_text}"
        self.vector_store.upsert_question(
            out.id,
            embed_text,
            user_id=user_id,
            tags=tags,
        )
        return out, analysis


class QueryMixin:
    """错题查询：关键词 + 语义双路检索、计数、详情、相似题。"""

    def list_questions(
        self,
        user_id: int,
        *,
        include_others: bool = False,
        tag: str | None = None,
        keyword: str | None = None,
        semantic: bool = True,
        offset: int = 0,
        limit: int | None = None,
    ) -> list[QuestionOut]:
        """关键词检索；开启语义搜索时用向量召回补充关键词未命中的题目。

        offset/limit 在过滤后应用；不传 limit 返回全部（界面默认），API 层分页传入。
        """
        with self._session() as repo:
            primary = repo.list_for_user(
                user_id,
                include_others=include_others,
                tag=tag,
                keyword=keyword,
                offset=offset,
                limit=limit,
            )
            results = {q.id: QuestionOut.from_orm_model(q) for q in primary}

        if keyword and semantic:
            scope = self._search_scope(user_id, include_others)
            hits = self.vector_store.semantic_search(keyword, user_ids=scope)
            hit_ids = [h.question_id for h in hits if h.question_id not in set(results)]
            if hit_ids:
                with self._session() as repo:
                    for q in repo.get_by_ids(hit_ids):
                        if q.user_id == user_id or include_others:
                            results[q.id] = QuestionOut.from_orm_model(q)

        return sorted(
            results.values(),
            key=lambda q: q.created_at or dt.datetime.min.replace(tzinfo=dt.timezone.utc),
            reverse=True,
        )

    def count_for_user(
        self,
        user_id: int,
        *,
        include_others: bool = False,
        tag: str | None = None,
        keyword: str | None = None,
    ) -> int:
        """过滤口径下的错题总数（API 分页用）。"""
        with self._session() as repo:
            return repo.count_for_user(
                user_id,
                include_others=include_others,
                tag=tag,
                keyword=keyword,
            )

    def get_question(self, question_id: int, user_id: int) -> QuestionOut | None:
        with self._session() as repo:
            q = repo.get_owned(question_id, user_id)
            return QuestionOut.from_orm_model(q) if q else None

    def similar_questions(self, question: QuestionOut, *, user_id: int) -> list[QuestionOut]:
        """「举一反三」：以本题解析文本为查询，召回最相近的历史错题。"""
        query_text = " ".join(
            [*(question.knowledge_points or []), *(question.tags or []), question.content_markdown]
        )
        hits: list = self.vector_store.similar_questions(
            query_text, user_ids=[user_id], exclude_id=question.id
        )
        if not hits:
            return []
        ordered_ids = [hit.question_id for hit in hits]
        with self._session() as repo:
            pool = {
                q.id: QuestionOut.from_orm_model(q)
                for q in repo.list_for_user(user_id)
                if q.id in set(ordered_ids)
            }
        return [pool[qid] for qid in ordered_ids if qid in pool]


class EditTagMixin:
    """编辑、删除与标签管理。"""

    def update_question(
        self,
        question_id: int,
        user_id: int,
        *,
        content_markdown: str | None = None,
        answer: str | None = None,
        tags: list[str] | None = None,
        user_note: str | None = None,
    ) -> QuestionOut | None:
        with self._session() as repo:
            question = repo.update(
                question_id,
                user_id,
                content_markdown=content_markdown,
                answer=answer,
                tags=tags,
                user_note=user_note,
            )
            out = QuestionOut.from_orm_model(question) if question else None

        if out is not None:
            self.vector_store.upsert_question(
                out.id,
                " ".join([*(out.knowledge_points or []), out.content_markdown, out.answer]),
                user_id=user_id,
                tags=out.tags,
            )
        return out

    def add_tags_to_many(
        self, question_ids: list[int], user_id: int, new_tags: list[str]
    ) -> int:
        """批量为错题追加标签，并同步向量库元数据。"""
        if not question_ids or not new_tags:
            return 0
        with self._session() as repo:
            changed = repo.add_tags(question_ids, user_id, new_tags)
            for qid in question_ids:
                question = repo.get_owned(qid, user_id)
                if question is not None:
                    self._reindex_owned(question)
        return changed

    def tag_usage(self, user_id: int) -> dict[str, int]:
        """用户错题标签使用统计：{标签: 题数}，按题数降序。"""
        questions = self.list_questions(user_id, semantic=False)
        usage: dict[str, int] = {}
        for question in questions:
            for tag in question.tags or []:
                usage[tag] = usage.get(tag, 0) + 1
        return dict(sorted(usage.items(), key=lambda kv: kv[1], reverse=True))

    def rename_tag(self, user_id: int, old: str, new: str) -> int:
        """全局重命名标签（含知识点），返回更新的题目数。"""
        old, new = old.strip(), new.strip()
        if not old or not new:
            raise ValueError("标签名不能为空")
        if old == new:
            return 0
        changed = 0
        with self._session() as repo:
            for question in repo.list_for_user(user_id):
                tags = list(question.tags or [])
                points = list(question.knowledge_points or [])
                new_tags = [new if t == old else t for t in tags]
                new_points = [new if t == old else t for t in points]
                if new_tags != tags or new_points != points:
                    question.tags = new_tags
                    question.knowledge_points = new_points
                    changed += 1
                    self._reindex_owned(question)
        return changed

    def delete_tag(self, user_id: int, tag: str) -> int:
        """从所有错题中移除某标签（同时清理知识点中的同名项）。"""
        tag = tag.strip()
        if not tag:
            raise ValueError("标签名不能为空")
        changed = 0
        with self._session() as repo:
            for question in repo.list_for_user(user_id):
                tags = [t for t in (question.tags or []) if t != tag]
                points = [t for t in (question.knowledge_points or []) if t != tag]
                if tags != (question.tags or []) or points != (question.knowledge_points or []):
                    question.tags = tags
                    question.knowledge_points = points
                    changed += 1
                    self._reindex_owned(question)
        return changed

    def delete_questions(self, question_ids: list[int], user_id: int) -> int:
        with self._session() as repo:
            deleted = repo.delete_many(question_ids, user_id)
        self.vector_store.delete_questions(question_ids)
        return deleted


class ReviewMixin:
    """复习调度与追问对话。"""

    def answer_followup(
        self,
        question_id: int,
        user_id: int,
        history: list[dict],
        user_question: str,
    ) -> str:
        """就一道已解析的错题进行多轮追问讲题（校验题目归属）。"""
        with self._session() as repo:
            question = repo.get_owned(question_id, user_id)
        if question is None:
            raise ValueError("错题不存在或无权访问")

        out = QuestionOut.from_orm_model(question)
        context = "\n".join(
            [
                "考点：" + "、".join(out.knowledge_points or []),
                "解析：\n" + out.content_markdown,
                "答案：" + out.answer,
                "变式题：" + (out.followup_question or "无"),
            ]
        )
        return self.ai.answer_followup(context, history, user_question)

    def due_questions(self, user_id: int) -> list[QuestionOut]:
        """到期错题；已掌握归档的题目不再进入每日复习池。"""
        with self._session() as repo:
            due = repo.due_for_review(user_id)
        outs = [QuestionOut.from_orm_model(q) for q in due]
        return [o for o in outs if not o.mastered]

    def recent_reviews(self, user_id: int, limit: int = 20) -> list[dict]:
        """最近的复习记录（新→旧），供复习历史视图使用。"""
        with self._session() as repo:
            logs = repo.review_logs_for_user(user_id)
            questions = {q.id: q for q in repo.list_for_user(user_id)}
        rows: list[dict] = []
        for log in reversed(logs[-limit:]):
            question = questions.get(log.question_id)
            rows.append(
                {
                    "reviewed_at": log.reviewed_at,
                    "grade": log.grade,
                    "interval_days": log.next_interval,
                    "snippet": (question.content_markdown[:50] if question else "（已删除）"),
                    "tags": (list(question.tags or []) if question else []),
                }
            )
        return rows

    def grade_review(self, question_id: int, user_id: int, grade: str) -> QuestionOut | None:
        with self._session() as repo:
            question = repo.get_owned(question_id, user_id)
            if question is None:
                return None
            schedule = self.scheduler.next_schedule(
                grade=grade,
                reps=question.reps,
                ease=question.ease,
                interval_days=question.interval_days,
            )
            updated = repo.apply_schedule(
                question_id,
                user_id,
                grade=grade,
                quality=schedule.quality,
                prev_interval=schedule.prev_interval,
                next_interval=schedule.next_interval,
                ease_after=schedule.ease_after,
                due_at=schedule.due_at,
            )
            return QuestionOut.from_orm_model(updated) if updated else None


class BackupMixin:
    """备份 / 恢复 / 导出。"""

    BACKUP_FORMAT = "mathmaster-backup"
    BACKUP_VERSION = 1

    def export_user_csv(self, user_id: int) -> str:
        """导出用户错题为 CSV（Excel 友好，UTF-8 BOM 兼容中文）。"""
        import csv

        questions = self.list_questions(user_id, semantic=False)
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(
            ["id", "created_at", "difficulty", "tags", "knowledge_points", "answer", "content"]
        )
        for q in questions:
            writer.writerow(
                [
                    q.id,
                    q.created_at.isoformat() if q.created_at else "",
                    q.difficulty,
                    " ".join(q.tags),
                    " ".join(q.knowledge_points),
                    q.answer,
                    q.content_markdown,
                ]
            )
        return "﻿" + buffer.getvalue()

    def export_user_data(self, user_id: int) -> dict:
        """导出用户全部错题为可移植 JSON（图片不包含，路径仅作参考）。"""
        questions = self.list_questions(user_id, semantic=False)
        return {
            "format": self.BACKUP_FORMAT,
            "version": self.BACKUP_VERSION,
            "exported_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "count": len(questions),
            "questions": [q.model_dump(mode="json") for q in questions],
        }

    def import_user_data(self, user_id: int, data: dict) -> int:
        """从备份 JSON 恢复错题（全部按手动录入处理，逐条校验）。返回导入数量。"""
        if data.get("format") != self.BACKUP_FORMAT:
            raise ValueError("备份文件格式不正确")
        items = data.get("questions")
        if not isinstance(items, list):
            raise ValueError("备份文件缺少 questions 列表")

        imported = 0
        for item in items:
            try:
                self.create_manual_question(
                    user_id,
                    content_markdown=str(item.get("content_markdown", "")).strip(),
                    answer=str(item.get("answer", "") or ""),
                    tags=[str(t) for t in (item.get("tags") or [])][:8],
                    knowledge_points=[str(t) for t in (item.get("knowledge_points") or [])][:8],
                    source="imported",
                )
                imported += 1
            except Exception as exc:  # noqa: BLE001 - 单条失败不阻断整体
                logger.warning("导入单条错题失败: %s", exc)
        return imported


class StatsMixin:
    """学情统计：个人看板 + 教师报表。"""

    def students_overview(self, teacher_id: int) -> list[dict]:
        """教师报表：每个学生的错题/复习/掌握度/活跃度汇总。仅教师可调用。"""
        with self._user_session() as users:
            caller = users.get_by_id(teacher_id)
            if caller is None:
                raise ValueError("用户不存在")
            if caller.role != "teacher":
                raise PermissionError("仅教师可查看学生总览")
            students = [u for u in users.list_users() if u.role == "student"]

        with self._session() as repo:
            questions = repo.list_for_user(teacher_id, include_others=True)
            logs = repo.all_review_logs()

        outs = [QuestionOut.from_orm_model(q) for q in questions]
        by_user: dict[int, list[QuestionOut]] = {}
        for out in outs:
            by_user.setdefault(out.user_id, []).append(out)
        logs_by_user: dict[int, list[tuple[str, float]]] = {}
        logs_by_user_id: dict[int, list] = {}
        now = dt.datetime.now(dt.timezone.utc)
        for log in logs:
            logs_by_user.setdefault(log.user_id, []).append(
                (log.grade, log.next_interval)
            )
            logs_by_user_id.setdefault(log.user_id, []).append(log)

        rows: list[dict] = []
        for student in students:
            items = by_user.get(student.id, [])
            student_logs = logs_by_user.get(student.id, [])
            student_log_objs = logs_by_user_id.get(student.id, [])
            tag_stats = build_tag_stats(items, {q.id: student_logs for q in items})
            mastery = (
                round(sum(s.mastery for s in tag_stats) / len(tag_stats), 3)
                if tag_stats
                else 0.0
            )
            due = len(
                [o for o in items if o.due_at is None or _aware(o.due_at) <= now]
            )
            reviewed_questions = {log.question_id for log in student_log_objs}
            last_active = max(
                [o.created_at for o in items if o.created_at]
                + [log.reviewed_at for log in student_log_objs],
                default=None,
            )
            rows.append(
                {
                    "user_id": student.id,
                    "username": student.username,
                    "total": len(items),
                    "due": due,
                    "reviewed": len(reviewed_questions),
                    "mastery": mastery,
                    "tags": len(tag_stats),
                    "last_active": last_active,
                }
            )
        rows.sort(key=lambda r: r["total"], reverse=True)
        return rows

    def dashboard_stats(self, user_id: int, *, include_others: bool = False) -> dict:
        with self._session() as repo:
            questions = repo.list_for_user(user_id, include_others=include_others)
            outs = [QuestionOut.from_orm_model(q) for q in questions]
            logs = repo.review_logs_for_user(user_id)

        logs_by_question: dict[int, list[tuple[str, float]]] = {}
        for log in logs:
            logs_by_question.setdefault(log.question_id, []).append(
                (log.grade, log.next_interval)
            )

        tag_stats: list[TagStat] = build_tag_stats(outs, logs_by_question)
        now = dt.datetime.now(dt.timezone.utc)
        # 待复习口径 = 自己名下到期（教师看全班总量，但复习池只含自己的题）
        due_count = len(
            [
                o
                for o in outs
                if o.user_id == user_id
                and (o.due_at is None or _aware(o.due_at) <= now)
            ]
        )
        mastered = len([o for o in outs if o.user_id == user_id and o.mastered])

        active_dates = {o.created_at for o in outs if o.created_at}
        active_dates.update(log.reviewed_at for log in logs)
        calendar_events = [o.created_at for o in outs if o.created_at] + [
            log.reviewed_at for log in logs
        ]
        return {
            "total": len(outs),
            "reviewed": len({log.question_id for log in logs}),
            "due": due_count,
            "mastered": mastered,
            "streak": study_streak(active_dates),
            "calendar": build_calendar(calendar_events),
            "accuracy_trend": build_accuracy_trend(logs),
            "weekly": weekly_report(outs, logs),
            "mastery_trend": mastery_trend(outs, logs),
            "tag_stats": tag_stats,
            "weak_tags": weak_tags(tag_stats),
            "activity": build_activity(outs),
        }
