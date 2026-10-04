"""数据体检与修复（用户价值迭代）。

检查三类真实使用中最常见的「数据漂移」：
1. 向量索引缺失：数据库有题、向量库没有 → 语义搜索/举一反三召回不到（修复=重建索引）；
2. 向量索引残留：题目已删、向量库还在 → 搜索可能返回幽灵结果（修复=清理）；
3. 孤儿图片文件：images 目录存在但没有任何题目引用的文件（修复=可选清理，回收磁盘）。

只读检查随时可跑；所有修复动作幂等且只作用于当前用户自己的数据。
"""
from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy.orm import Session, sessionmaker

from backend.models.schemas import QuestionOut
from backend.services.rag import QuestionVectorStore
from backend.utils.logging import get_logger

logger = get_logger(__name__)


class DataHealthService:
    def __init__(
        self,
        session_factory: sessionmaker | Callable[[], Iterator[Session]] | None = None,
        vector_store: QuestionVectorStore | None = None,
    ):
        self._session_factory = session_factory
        self._vector_store = vector_store

    @property
    def vector_store(self) -> QuestionVectorStore:
        if self._vector_store is None:
            self._vector_store = QuestionVectorStore()
        return self._vector_store

    @contextmanager
    def _session(self) -> Iterator[Session]:
        from backend.database import session_scope

        with session_scope(self._session_factory) as session:
            yield session

    def _questions(self, user_id: int) -> list[QuestionOut]:
        with self._session() as session:
            from backend.repositories.questions import QuestionRepository

            repo = QuestionRepository(session)
            return [QuestionOut.from_orm_model(q) for q in repo.list_for_user(user_id)]

    @staticmethod
    def _embed_text(question: QuestionOut) -> str:
        return " ".join(
            [
                *(question.knowledge_points or []),
                question.content_markdown,
                question.answer or "",
                *(question.tags or []),
            ]
        )

    def check(self, user_id: int) -> dict:
        """全量体检：返回可直出的报告字典（各项均带 human 可读文案）。"""
        from backend.utils.paths import resolve_image_path

        questions = self._questions(user_id)
        db_ids = {q.id for q in questions}
        # 存储端可能是相对路径或历史绝对路径——统一解析回绝对再做引用比对
        referenced_images = {
            str(resolve_image_path(q.image_path).resolve())
            for q in questions
            if q.image_path
        }

        report: dict = {
            "question_count": len(questions),
            "vector_available": self.vector_store.is_available(),
        }

        if report["vector_available"]:
            indexed = self.vector_store.indexed_ids_for_user(user_id)
            missing = sorted(db_ids - indexed)
            stale = sorted(indexed - db_ids)
            report["missing_index_ids"] = missing
            report["stale_index_ids"] = stale
            report["missing_index"] = len(missing)
            report["stale_index"] = len(stale)
            report["issues"] = len(missing) + len(stale)
        else:
            report.update(
                missing_index_ids=[],
                stale_index_ids=[],
                missing_index=0,
                stale_index=0,
                issues=0,
                note="向量库不可用（已降级关键词检索），跳过索引核对",
            )

        images_dir = self._images_dir(user_id)
        orphans: list[str] = []
        total_orphan_bytes = 0
        from backend.config import get_settings

        if get_settings().storage_backend == "s3":
            # s3 模式图片在远端桶内，本地 images 目录不再是事实来源
            report["note_images"] = (
                "s3 对象存储模式下跳过本地孤儿图片体检（对象在远端桶内管理）"
            )
        elif images_dir.exists():
            for path in images_dir.iterdir():
                if path.is_file() and str(path.resolve()) not in referenced_images:
                    orphans.append(str(path))
                    total_orphan_bytes += path.stat().st_size
        report["orphan_images"] = orphans
        report["orphan_image_count"] = len(orphans)
        report["orphan_image_mb"] = round(total_orphan_bytes / (1024 * 1024), 2)
        if report["vector_available"]:
            report["issues"] += len(orphans)
        return report

    def repair_index(self, user_id: int) -> dict:
        """修复向量索引：补齐缺失 + 清理残留，返回 {reindexed, removed}。"""
        questions = self._questions(user_id)
        reindexed = 0
        for question in questions:
            ok = self.vector_store.upsert_question(
                question.id,
                self._embed_text(question),
                user_id=question.user_id,
                tags=question.tags,
                created_at=question.created_at,
            )
            reindexed += 1 if ok else 0
        stale = sorted(self.vector_store.indexed_ids_for_user(user_id) - {q.id for q in questions})
        if stale:
            self.vector_store.delete_questions(stale)
        logger.info(
            "向量索引修复完成 user=%s reindexed=%s removed=%s", user_id, reindexed, len(stale)
        )
        return {"reindexed": reindexed, "removed": len(stale)}

    def cleanup_orphan_images(self, user_id: int) -> int:
        """删除当前用户未被任何题目引用的图片文件，返回删除数。"""
        report = self.check(user_id)
        removed = 0
        for path_str in report["orphan_images"]:
            try:
                Path(path_str).unlink()
                removed += 1
            except OSError as exc:
                logger.warning("孤儿图片删除失败 %s: %s", path_str, exc)
        return removed

    @staticmethod
    def _images_dir(user_id: int) -> Path:
        from backend.config import get_settings

        return get_settings().data_dir / "images" / f"u{user_id}"
