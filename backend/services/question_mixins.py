"""QuestionService 的 Mixin 拆分：按领域分组的方法集合。

QuestionService 由这些 Mixin 组合而成（见 question_service.py），
公共 API 与拆分前完全一致。CoreMixin 提供共享基础设施。
"""
from __future__ import annotations

import datetime as dt
import hashlib
import io
import re
import time
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
from backend.services.entry_types import EntryResult
from backend.services.mastery import KPMastery, MasteryEngine, PlanItem
from backend.services.rag import QuestionVectorStore, _log_pipeline, _similarity
from backend.services.review import ReviewScheduler
from backend.services.stats import (
    build_accuracy_trend,
    build_activity,
    build_calendar,
    build_difficulty_distribution,
    build_tag_stats,
    mastery_trend,
    study_streak,
    weak_tags,
    weekly_report,
)
from backend.utils.logging import get_logger
from backend.utils.paths import to_stored_path

if TYPE_CHECKING:  # pragma: no cover
    from sqlalchemy.orm import Session, sessionmaker

logger = get_logger("questions")

_DOCX_SEGMENT_CHARS = 4000  # 每段送 AI 的文本上限（规避单次输出截断）


def _segment_text(text: str, max_chars: int = _DOCX_SEGMENT_CHARS) -> list[str]:
    """把长文档按段落边界切成 ~max_chars 的段（不在公式/句子中间截断）。"""
    if len(text) <= max_chars:
        return [text]
    segments: list[str] = []
    current = ""
    for para in text.split("\n\n"):
        para = para.strip()
        if not para:
            continue
        if current and len(current) + len(para) + 2 > max_chars:
            segments.append(current)
            current = para
        else:
            current = f"{current}\n\n{para}" if current else para
    if current:
        segments.append(current)
    return segments or [text]


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
        self.mastery = MasteryEngine(session_factory)

    def _sync_kp_links(self, repo: QuestionRepository, question_id: int, names: list[str]) -> None:
        """把题目上的知识点名称同步进规范化 M2M（在当前事务内执行）。"""
        from backend.services.mastery import sync_question_links

        sync_question_links(repo.session, question_id, names)

    @contextmanager
    def _session(self) -> Iterator[QuestionRepository]:
        from backend.database import session_scope

        with session_scope(self._session_factory) as session:
            yield QuestionRepository(session)

    @contextmanager
    def _user_session(self) -> Iterator[object]:
        from backend.database import session_scope
        from backend.repositories.users import UserRepository

        with session_scope(self._session_factory) as session:
            yield UserRepository(session)

    def _search_scope(self, user_id: int, include_others: bool) -> list[int]:
        """语义检索的可见范围：普通用户仅自己；教师为 自己 + 所教班级学生。

        教师尚未建立班级时保持旧行为（可见全部学生），保证向后兼容。
        """
        if not include_others:
            return [user_id]
        from backend.services.class_service import ClassService

        with self._user_session() as users:
            all_students = [u.id for u in users.list_users() if u.role == "student"]
        class_students = ClassService().student_ids_for_teacher(user_id)
        return [user_id, *(class_students or all_students)]

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

    def _verify_analysis(self, analysis: QuestionAnalysis) -> dict:
        """对 AI 解析结果运行数学验证，返回 repo.create 可用的 verification 字典。"""
        from backend.services.math_verifier import verify_answer

        try:
            result = verify_answer(analysis.analysis, "", analysis.answer)
        except Exception as exc:  # noqa: BLE001 - 验证失败不影响保存
            logger.warning("数学验证异常: %s", exc)
            return {
                "status": "uncertain",
                "confidence": 0.0,
                "methods": [],
                "verified_at": dt.datetime.now(dt.timezone.utc),
            }
        return {
            "status": result.status,
            "confidence": result.confidence,
            "methods": result.methods,
            "details": result.details,
            "verified_at": dt.datetime.now(dt.timezone.utc),
        }

    def analyze_and_save_dedup(
        self,
        user_id: int,
        image_bytes: bytes,
        *,
        mime_type: str = "image/jpeg",
        user_tags: list[str] | None = None,
        hint: str = "",
    ) -> EntryResult:
        """带去重的录题：同图已录入时跳过 AI 调用，直接返回既有记录。"""
        image_hash = hashlib.sha256(image_bytes).hexdigest()
        with self._session() as repo:
            existing = repo.find_by_image_hash(user_id, image_hash)
        if existing is not None:
            out = QuestionOut.from_orm_model(existing)
            analysis = QuestionAnalysis(
                knowledge_points=list(out.knowledge_points or []),
                analysis=out.content_markdown,
                answer=out.answer,
                difficulty=out.difficulty,  # type: ignore[arg-type]
                tags=list(out.tags or []),
                mistake_cause="",
                followup_question=out.followup_question or "",
            )
            logger.info("重复图片 question=%s user=%s，直接复用", out.id, user_id)
            return EntryResult(question=out, analysis=analysis, duplicated=True)

        out, analysis = self.analyze_and_save(
            user_id,
            image_bytes,
            mime_type=mime_type,
            user_tags=user_tags,
            hint=hint,
            image_hash=image_hash,
        )
        return EntryResult(question=out, analysis=analysis, duplicated=False)

    def add_questions_from_docx(
        self,
        user_id: int,
        docx_bytes: bytes,
        *,
        tags: list[str] | None = None,
        hint: str = "",
        max_questions: int = 100,
    ) -> dict:
        """Word 文档批量导入：提取文本 → 结构识别优先/AI 分段拆题 → 逐题入库。

        拆分策略（借鉴同类项目的确定性优先模式）：
        1) 行首题号识别成功 → 直接拆题入库，零 AI 调用、零超时风险；
        2) 识别不到题号 → 按段落边界分段（每段 ~4000 字）走 AI 拆题，
           单段失败跳过不阻断整批；拆题调用自带重试。
        返回 {"total", "imported", "items", "mode", "failed_segments"}。
        """
        from backend.services.docx_import import (
            extract_docx_text,
            split_by_question_numbers,
        )

        text = extract_docx_text(docx_bytes)

        mode = "题号结构识别（零 AI 调用）"
        failed_segments = 0
        numbered_parts = split_by_question_numbers(text)
        if numbered_parts:
            chunks = [
                {"content": part, "answer": "", "knowledge_points": [], "difficulty": "medium"}
                for part in numbered_parts
            ]
        else:
            mode = "AI 分段拆题"
            chunks = []
            for segment in _segment_text(text):
                try:
                    chunks.extend(self.ai.split_questions(segment))
                except Exception as exc:  # noqa: BLE001 - 单段失败跳过，不阻断整批
                    failed_segments += 1
                    logger.warning("分段拆题失败（跳过该段 %s 字）: %s", len(segment), exc)
        if len(chunks) > max_questions:
            logger.warning("拆出 %s 题超过上限，截断为 %s 题", len(chunks), max_questions)
            chunks = chunks[:max_questions]

        imported: list = []
        for chunk in chunks:
            try:
                difficulty = chunk.get("difficulty") or "medium"
                out = self.create_manual_question(
                    user_id,
                    content_markdown=str(chunk.get("content", "")).strip(),
                    answer=str(chunk.get("answer", "") or ""),
                    tags=tags or [],
                    knowledge_points=[str(k) for k in (chunk.get("knowledge_points") or [])][:3],
                    source="word",
                    difficulty=str(difficulty) if difficulty in {"easy", "medium", "hard"} else "medium",
                )
                imported.append(out)
            except Exception as exc:  # noqa: BLE001 - 单题失败不阻断整批
                logger.warning("Word 导入单题失败: %s", exc)
        logger.info("Word 导入完成 user=%s 拆出 %s 题，入库 %s 题（%s，失败段 %s）", user_id, len(chunks), len(imported), mode, failed_segments)
        return {"total": len(chunks), "imported": len(imported), "items": imported, "mode": mode, "failed_segments": failed_segments}

    def create_manual_question(
        self,
        user_id: int,
        *,
        content_markdown: str,
        answer: str = "",
        tags: list[str] | None = None,
        knowledge_points: list[str] | None = None,
        source: str = "manual",
        difficulty: str = "medium",
        ai_analyze: bool = False,
        hint: str = "",
        image_hash: str | None = None,
    ) -> QuestionOut:
        """手动录入文本错题：入库 + 向量索引；可选 AI 文本解析补全空缺标注。"""
        if not content_markdown or not content_markdown.strip():
            raise ValueError("题目内容不能为空")
        if difficulty not in {"easy", "medium", "hard"}:
            raise ValueError("难度只能是 easy / medium / hard")
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
                difficulty=difficulty,
                followup_question=followup,
                source=source,
                image_hash=image_hash,
            )
            self._sync_kp_links(repo, question.id, clean_points)
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
        image_hash: str | None = None,
    ) -> tuple[QuestionOut, QuestionAnalysis]:
        """完整录入链路：AI 解析 → 数学验证 → 图片落盘 → 数据库 → 向量索引。

        image_hash：调用方（analyze_and_save_dedup）预算好的原图哈希，入库供去重。
        """
        analysis = self.ai.analyze_question(image_bytes, mime_type, hint)
        tags = analysis.merged_tags(user_tags or [])

        verification = self._verify_analysis(analysis)
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
                image_path=to_stored_path(image_path),
                ocr_text=ocr_text,
                image_hash=image_hash,
                verification=verification,
            )
            self._sync_kp_links(repo, question.id, analysis.knowledge_points)
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


class EntryResultMixin:
    """dedup 录题结果类型挂载点（保持 EntryResult 从 entry_types 导入）。"""


class QueryMixin:
    """错题查询：关键词 + 语义双路检索、计数、详情、相似题。"""

    def list_questions(
        self,
        user_id: int,
        *,
        include_others: bool = False,
        tag: str | None = None,
        keyword: str | None = None,
        difficulty: str | None = None,
        starred: bool = False,
        semantic: bool = True,
        offset: int = 0,
        limit: int | None = None,
    ) -> list[QuestionOut]:
        """关键词检索；开启语义搜索时执行完整混合管线：
        Keyword Top-N + Dense Top-N → RRF → Hydrate 全候选 → 可选 Rerank → 阈值过滤。

        offset/limit 在管线末端应用；不传 limit 返回全部（界面默认），API 层分页传入。
        """
        started = time.perf_counter()
        settings = self.settings
        candidate_k = settings.rag_candidate_k

        with self._session() as repo:
            # Keyword 通道：SQL 下推过滤，取深候选池
            primary = repo.list_for_user(
                user_id,
                include_others=include_others,
                tag=tag,
                keyword=keyword,
                difficulty=difficulty,
                starred=starred,
                limit=candidate_k if (keyword and semantic) else None,
            )
            results = {q.id: QuestionOut.from_orm_model(q) for q in primary}
            keyword_ids = [q.id for q in primary]

        if not (keyword and semantic):
            # 纯关键词/无关键词：保持时间排序，管线末端应用分页
            ordered = sorted(
                (q for q in results.values() if difficulty is None or q.difficulty == difficulty),
                key=lambda q: q.created_at or dt.datetime.min.replace(tzinfo=dt.timezone.utc),
                reverse=True,
            )
            if offset:
                ordered = ordered[offset:]
            if limit is not None:
                ordered = ordered[:limit]
            return ordered

        # Dense 通道：深候选池 + 相似度阈值
        scope = self._search_scope(user_id, include_others)
        vector_hits = self.vector_store.hybrid_dense_search(
            keyword,
            user_ids=scope,
            candidate_k=candidate_k,
            min_similarity=settings.rag_min_similarity or None,
        )
        vector_ids = [h.question_id for h in vector_hits]

        # RRF 融合两路候选
        from backend.services.fusion import rerank, rrf_fuse

        fused_ids = rrf_fuse(vector_ids, keyword_ids, top_k=candidate_k)

        # Hydrate：一次性取出全部融合候选（reranker 必须看到完整候选集）
        missing = [qid for qid in fused_ids if qid not in results]
        if missing:
            with self._session() as repo:
                for q in repo.get_by_ids(missing):
                    if q.user_id == user_id or include_others:
                        results[q.id] = QuestionOut.from_orm_model(q)

        # 重排：在完整候选集上精排（未配置则直通融合排序；失败降级为融合序）
        reranked_ids: list[int] | None = None
        if settings.rerank_base_url and fused_ids:
            try:
                docs = [results[qid].content_markdown for qid in fused_ids if qid in results]
                reranked = rerank(
                    keyword,
                    docs,
                    base_url=settings.rerank_base_url,
                    api_key=settings.rerank_api_key,
                    model=settings.rerank_model,
                    top_k=settings.rag_top_k,
                )
                if reranked:
                    ordered = [fused_ids[i] for i, _ in reranked if i < len(fused_ids)]
                    reranked_ids = ordered + [qid for qid in fused_ids if qid not in ordered]
                    fused_ids = reranked_ids
            except Exception as exc:  # noqa: BLE001 - 重排失败降级为融合排序
                logger.warning("重排失败，使用融合排序: %s", exc)

        # 相似度阈值：仅过滤「只来自向量路」且低于阈值的候选
        pre_filter_fused = list(fused_ids)
        if settings.rag_min_similarity > 0:
            sim_by_id = {h.question_id: _similarity(h.distance) for h in vector_hits}
            vector_only = set(vector_ids) - set(keyword_ids)
            fused_ids = [
                qid
                for qid in fused_ids
                if qid not in vector_only
                or sim_by_id.get(qid, 1.0) >= settings.rag_min_similarity
            ]

        latency_ms = round((time.perf_counter() - started) * 1000)
        _log_pipeline(
            settings.rag_debug_log,
            query=keyword,
            user_id=user_id,
            dense_ids=vector_ids,
            keyword_ids=keyword_ids,
            fused_ids=fused_ids,
            reranked=reranked_ids is not None,
            latency_ms=latency_ms,
        )

        # 管线末端应用 offset/limit；融合外候选（理论不存在）按时间排尾，保证不丢题。
        # rest 基于过滤前的候选集，但被阈值/过滤明确剔除的题不会回流。
        ordered_results = [results[qid] for qid in fused_ids if qid in results]
        ordered_results = [
            q
            for q in ordered_results
            if (difficulty is None or q.difficulty == difficulty)
            and (not starred or q.starred)
        ]
        filtered_out = set(pre_filter_fused) - set(fused_ids)
        fused_set = set(fused_ids)
        rest = sorted(
            (
                q
                for qid, q in results.items()
                if qid not in fused_set
                and qid not in filtered_out
                and (difficulty is None or q.difficulty == difficulty)
                and (not starred or q.starred)
            ),
            key=lambda q: q.created_at or dt.datetime.min.replace(tzinfo=dt.timezone.utc),
            reverse=True,
        )
        ordered_results.extend(rest)

        if offset:
            ordered_results = ordered_results[offset:]
        if limit is not None:
            ordered_results = ordered_results[:limit]
        return ordered_results

    def count_for_user(
        self,
        user_id: int,
        *,
        include_others: bool = False,
        tag: str | None = None,
        keyword: str | None = None,
        difficulty: str | None = None,
        starred: bool = False,
    ) -> int:
        """过滤口径下的错题总数（API 分页用）。"""
        with self._session() as repo:
            return repo.count_for_user(
                user_id,
                include_others=include_others,
                tag=tag,
                keyword=keyword,
                difficulty=difficulty,
                starred=starred,
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
        knowledge_points: list[str] | None = None,
        user_note: str | None = None,
    ) -> QuestionOut | None:
        with self._session() as repo:
            question = repo.update(
                question_id,
                user_id,
                content_markdown=content_markdown,
                answer=answer,
                tags=tags,
                knowledge_points=knowledge_points,
                user_note=user_note,
            )
            if question is not None and knowledge_points is not None:
                self._sync_kp_links(repo, question.id, knowledge_points)
            out = QuestionOut.from_orm_model(question) if question else None

        if out is not None:
            self.vector_store.upsert_question(
                out.id,
                " ".join([*(out.knowledge_points or []), out.content_markdown, out.answer or ""]),
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

    def set_difficulty_many(
        self, question_ids: list[int], user_id: int, difficulty: str
    ) -> int:
        """批量为错题设置难度（校验取值，SQL 下推），返回处理数量。"""
        if difficulty not in {"easy", "medium", "hard"}:
            raise ValueError("难度只能是 easy / medium / hard")
        if not question_ids:
            return 0
        with self._session() as repo:
            return repo.set_difficulty_many(question_ids, user_id, difficulty)

    def remove_tag_from_many(
        self, question_ids: list[int], user_id: int, tag: str
    ) -> int:
        """从一组错题移除指定标签（含知识点同名项）并同步向量元数据，返回处理数量。"""
        tag = (tag or "").strip()
        if not tag:
            raise ValueError("标签名不能为空")
        if not question_ids:
            return 0
        with self._session() as repo:
            changed = repo.remove_tag_many(question_ids, user_id, tag)
            for qid in question_ids:
                question = repo.get_owned(qid, user_id)
                if question is not None:
                    self._reindex_owned(question)
        return changed

    def toggle_star(self, question_id: int, user_id: int) -> bool | None:
        """切换错题星标，返回切换后的状态；题目不存在或无权访问返回 None。"""
        with self._session() as repo:
            question = repo.get_owned(question_id, user_id)
            if question is None:
                return None
            new_state = not bool(question.starred)
            repo.set_starred(question_id, user_id, new_state)
            return new_state

    def snapshot_review_state(self, question_id: int, user_id: int) -> dict | None:
        """评分前快照 SM-2 状态与最近复习日志 ID（撤销用）。"""

        with self._session() as repo:
            question = repo.get_owned(question_id, user_id)
            if question is None:
                return None
            logs = list(question.review_logs)
            last_log_id = logs[-1].id if logs else None
            return {
                "reps": int(question.reps),
                "ease": float(question.ease),
                "interval_days": float(question.interval_days),
                "due_at": question.due_at.isoformat() if question.due_at else None,
                "last_reviewed_at": (
                    question.last_reviewed_at.isoformat()
                    if question.last_reviewed_at
                    else None
                ),
                "last_log_id": last_log_id,
            }

    def restore_review_state(
        self, question_id: int, user_id: int, snapshot: dict
    ) -> bool:
        """撤销一次评分：恢复 SM-2 状态并删除评分新生成的那条复习日志。

        snapshot 在评分前取得（last_log_id 指向更早的历史日志）；
        恢复时删除的是当前最新日志——即被撤销的那次评分所写入的行。
        """

        with self._session() as repo:
            question = repo.get_owned(question_id, user_id)
            if question is None:
                return False
            question.reps = int(snapshot["reps"])
            question.ease = float(snapshot["ease"])
            question.interval_days = float(snapshot["interval_days"])
            question.due_at = (
                dt.datetime.fromisoformat(snapshot["due_at"])
                if snapshot["due_at"]
                else None
            )
            question.last_reviewed_at = (
                dt.datetime.fromisoformat(snapshot["last_reviewed_at"])
                if snapshot["last_reviewed_at"]
                else None
            )
            logs = list(question.review_logs)
            if logs:
                newest = logs[-1]
                if newest.id != snapshot.get("last_log_id"):
                    repo.session.delete(newest)
        return True

    def today_graded_count(self, user_id: int) -> int:
        """今日已评分次数（看板每日目标进度）。"""
        with self._session() as repo:
            today_start = dt.datetime.now().astimezone().replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            return repo.today_graded_count(user_id, today_start)

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
                    if new_points != points:
                        self._sync_kp_links(repo, question.id, new_points)
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
                    if points != (question.knowledge_points or []):
                        self._sync_kp_links(repo, question.id, points)
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

    def mastery_by_question(self, user_id: int) -> dict[int, float]:
        """单题掌握度映射（0~1，仅有复习记录的题），供错题本筛选与角标使用。"""
        from collections import defaultdict

        from backend.services.mastery import question_mastery

        with self._session() as repo:
            logs = repo.review_logs_for_user(user_id)
        logs_by_question: dict[int, list] = defaultdict(list)
        for log in logs:
            logs_by_question[log.question_id].append(log)
        return {
            qid: question_mastery(q_logs)
            for qid, q_logs in logs_by_question.items()
        }

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
        """从备份 JSON 恢复错题（全部按手动录入处理，逐条校验）。

        带 image_hash 的条目按哈希去重（幂等：同一备份可重复导入不产生重复题）。
        返回实际新导入数量。
        """
        if data.get("format") != self.BACKUP_FORMAT:
            raise ValueError("备份文件格式不正确")
        items = data.get("questions")
        if not isinstance(items, list):
            raise ValueError("备份文件缺少 questions 列表")

        imported = 0
        for item in items:
            try:
                image_hash = item.get("image_hash") or None
                if image_hash:
                    with self._session() as repo:
                        if repo.find_by_image_hash(user_id, str(image_hash)) is not None:
                            continue  # 已存在，幂等跳过
                self.create_manual_question(
                    user_id,
                    content_markdown=str(item.get("content_markdown", "")).strip(),
                    answer=str(item.get("answer", "") or ""),
                    tags=[str(t) for t in (item.get("tags") or [])][:8],
                    knowledge_points=[str(t) for t in (item.get("knowledge_points") or [])][:8],
                    source="imported",
                    image_hash=str(image_hash) if image_hash else None,
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
        # 多租户收紧：教师建了班级后，总览仅覆盖自己班级的学生（无班级保持全量）
        from backend.services.class_service import ClassService

        class_students = ClassService().student_ids_for_teacher(teacher_id)
        if class_students:
            outs = [o for o in outs if o.user_id in class_students]
            students = [u for u in students if u.id in class_students]
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
            "difficulty": build_difficulty_distribution(outs),
            "weekly": weekly_report(outs, logs),
            "mastery_trend": mastery_trend(outs, logs),
            "tag_stats": tag_stats,
            "weak_tags": weak_tags(tag_stats),
            "activity": build_activity(outs),
        }


class MasteryMixin:
    """知识点掌握度画像与自适应复习计划（Batch 04/05 门面）。"""

    def mastery_profile(self, user_id: int, limit: int | None = None) -> list[KPMastery]:
        """知识点掌握度画像，薄弱者排前。"""
        return self.mastery.profile(user_id, limit=limit)

    def today_plan(self, user_id: int, size: int = 10) -> list[PlanItem]:
        """今日复习计划：SM-2 到期优先 + 薄弱知识点加固。"""
        return self.mastery.today_plan(user_id, size=size)
