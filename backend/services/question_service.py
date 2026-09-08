"""错题应用服务：编排 AI 解析、存储、向量索引、检索与复习的完整链路。

界面层只与本模块交互，不直接触碰仓储 / AI / 向量库实现。
Session 策略：每次公开操作独立开短事务（session-per-operation），
与 Streamlit「脚本反复重跑 + 多线程渲染」的执行模型兼容。
"""
from __future__ import annotations

import datetime as dt
import re
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy.orm import Session, sessionmaker

from backend.config import get_settings
from backend.models.schemas import QuestionAnalysis, QuestionOut, TagStat
from backend.repositories.questions import QuestionRepository
from backend.services.ai import get_ai_service
from backend.services.ai.base import BaseAIProvider
from backend.services.rag import QuestionVectorStore, RagHit
from backend.services.review import ReviewScheduler
from backend.services.stats import build_activity, build_tag_stats, weak_tags
from backend.utils.logging import get_logger

logger = get_logger("questions")


class QuestionService:
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

    # ---------- 录入 ----------
    def create_manual_question(
        self,
        user_id: int,
        *,
        content_markdown: str,
        answer: str = "",
        tags: list[str] | None = None,
        knowledge_points: list[str] | None = None,
        source: str = "manual",
    ) -> QuestionOut:
        """手动录入文本错题：入库 + 向量索引，跳过视觉模型。"""
        if not content_markdown or not content_markdown.strip():
            raise ValueError("题目内容不能为空")
        clean_tags = [t.strip() for t in (tags or []) if t.strip()]
        clean_points = [t.strip() for t in (knowledge_points or []) if t.strip()]
        with self._session() as repo:
            question = repo.create(
                user_id,
                content_markdown=content_markdown,
                answer=answer,
                knowledge_points=clean_points,
                tags=clean_tags,
                source=source,
            )
            out = QuestionOut.from_orm_model(question)

        self.vector_store.upsert_question(
            out.id,
            " ".join([*clean_points, content_markdown, answer, *clean_tags]),
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
        """完整录入链路：AI 解析 → 图片落盘 → 数据库 → 向量索引。"""
        analysis = self.ai.analyze_question(image_bytes, mime_type, hint)
        tags = analysis.merged_tags(user_tags or [])

        image_path = self._persist_image(user_id, image_bytes)
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
            )
            out = QuestionOut.from_orm_model(question)

        self.vector_store.upsert_question(
            out.id,
            self._embeddable_text(analysis),
            user_id=user_id,
            tags=tags,
        )
        return out, analysis

    def _persist_image(self, user_id: int, image_bytes: bytes) -> Path:
        user_dir = self.settings.data_dir / "images" / f"u{user_id}"
        user_dir.mkdir(parents=True, exist_ok=True)
        path = user_dir / f"{dt.datetime.now():%Y%m%d_%H%M%S}_{uuid.uuid4().hex[:8]}.jpg"
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

    # ---------- 检索 ----------
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
            hits = self.vector_store.semantic_search(keyword, user_id=user_id)
            hit_ids = {hit.question_id for hit in hits} - set(results)
            with self._session() as repo:
                for qid in hit_ids:
                    q = repo.get_owned(qid, user_id)
                    if q:
                        results[qid] = QuestionOut.from_orm_model(q)

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
        hits: list[RagHit] = self.vector_store.similar_questions(
            query_text, user_id=user_id, exclude_id=question.id
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

    # ---------- 编辑 / 删除 ----------
    def update_question(
        self,
        question_id: int,
        user_id: int,
        *,
        content_markdown: str | None = None,
        answer: str | None = None,
        tags: list[str] | None = None,
    ) -> QuestionOut | None:
        with self._session() as repo:
            question = repo.update(
                question_id,
                user_id,
                content_markdown=content_markdown,
                answer=answer,
                tags=tags,
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

    def delete_questions(self, question_ids: list[int], user_id: int) -> int:
        with self._session() as repo:
            deleted = repo.delete_many(question_ids, user_id)
        self.vector_store.delete_questions(question_ids)
        return deleted

    # ---------- 追问对话 ----------
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

        from backend.models.schemas import QuestionOut

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

    # ---------- 复习 ----------
    def due_questions(self, user_id: int) -> list[QuestionOut]:
        with self._session() as repo:
            return [QuestionOut.from_orm_model(q) for q in repo.due_for_review(user_id)]

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

    # ---------- 备份 / 恢复 ----------
    BACKUP_FORMAT = "mathmaster-backup"
    BACKUP_VERSION = 1

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

    # ---------- 统计 ----------
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

        # build_tag_stats 只读所需字段，QuestionOut 满足鸭子类型
        tag_stats: list[TagStat] = build_tag_stats(outs, logs_by_question)
        now = dt.datetime.now(dt.timezone.utc)
        due_count = len(
            [o for o in outs if o.due_at is None or _aware(o.due_at) <= now]
        )
        return {
            "total": len(outs),
            "reviewed": len({log.question_id for log in logs}),
            "due": due_count,
            "tag_stats": tag_stats,
            "weak_tags": weak_tags(tag_stats),
            "activity": build_activity(outs),
        }


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
