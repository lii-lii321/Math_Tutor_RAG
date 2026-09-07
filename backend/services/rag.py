"""RAG 服务：基于 ChromaDB 的错题向量库。

能力：
1. 错题解析文本入库（含知识点/标签元数据）
2. 「举一反三」相似题召回
3. 错题本语义搜索（自然语言找题，不依赖标签完全匹配）

嵌入模型策略：
- 配置了 EMBEDDING_BASE_URL/KEY → 使用 OpenAI 兼容嵌入接口（如 BGE-M3）
- 未配置 → 使用 ChromaDB 内置本地嵌入模型，零外部依赖

任何环节故障均自动降级为关键词检索，保证主流程不被向量库阻断。
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from backend.config import Settings, get_settings
from backend.utils.logging import get_logger

logger = get_logger("rag")


@dataclass
class RagHit:
    question_id: int
    distance: float
    tags: list[str] = field(default_factory=list)
    snippet: str = ""


class QuestionVectorStore:
    """ChromaDB 持久化向量库的轻量封装。"""

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self._collection = None
        self._available: bool | None = None  # None = 未探测

    # ---------- 惰性初始化 ----------
    def _ensure_collection(self):
        if self._collection is not None:
            return self._collection
        if not self.settings.rag_enabled:
            self._available = False
            return None
        try:
            import chromadb
            from chromadb.utils import embedding_functions

            client = chromadb.PersistentClient(path=str(self.settings.chroma_dir))
            embed_fn = self._build_embedding_fn(embedding_functions)
            self._collection = client.get_or_create_collection(
                name="questions",
                embedding_function=embed_fn,
                metadata={"hnsw:space": "cosine"},
            )
            self._available = True
        except Exception as exc:  # noqa: BLE001 - 向量库故障不阻断主流程
            logger.warning("向量库初始化失败，已降级为关键词检索: %s", exc)
            self._collection = None
            self._available = False
        return self._collection

    def _build_embedding_fn(self, embedding_functions):
        if self.settings.embedding_base_url and self.settings.embedding_api_key:
            logger.info("使用远程嵌入模型: %s", self.settings.embedding_model)
            return embedding_functions.OpenAIEmbeddingFunction(
                api_key=self.settings.embedding_api_key,
                api_base=self.settings.embedding_base_url,
                model_name=self.settings.embedding_model,
            )
        logger.info("使用 ChromaDB 内置本地嵌入模型")
        return embedding_functions.DefaultEmbeddingFunction()

    def is_available(self) -> bool:
        return bool(self._ensure_collection() is not None)

    # ---------- 写入 / 删除 ----------
    def upsert_question(
        self,
        question_id: int,
        text: str,
        *,
        user_id: int,
        tags: list[str],
        created_at: dt.datetime | None = None,
    ) -> bool:
        collection = self._ensure_collection()
        if collection is None or not text.strip():
            return False
        try:
            collection.upsert(
                ids=[str(question_id)],
                documents=[text[:4000]],
                metadatas=[
                    {
                        "user_id": user_id,
                        "tags": ",".join(tags),
                        "created": (created_at or dt.datetime.now(dt.timezone.utc)).strftime(
                            "%Y-%m-%d"
                        ),
                    }
                ],
            )
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning("向量入库失败 (question=%s): %s", question_id, exc)
            return False

    def delete_questions(self, question_ids: list[int]) -> None:
        collection = self._ensure_collection()
        if collection is None or not question_ids:
            return
        try:
            collection.delete(ids=[str(qid) for qid in question_ids])
        except Exception as exc:  # noqa: BLE001
            logger.warning("向量删除失败: %s", exc)

    # ---------- 检索 ----------
    def similar_questions(
        self,
        query_text: str,
        *,
        user_id: int,
        exclude_id: int | None = None,
        top_k: int | None = None,
    ) -> list[RagHit]:
        return self._query(query_text, user_id=user_id, exclude_id=exclude_id, top_k=top_k)

    def semantic_search(self, query: str, *, user_id: int, top_k: int = 20) -> list[RagHit]:
        return self._query(query, user_id=user_id, exclude_id=None, top_k=top_k)

    def _query(
        self,
        query_text: str,
        *,
        user_id: int,
        exclude_id: int | None,
        top_k: int | None,
    ) -> list[RagHit]:
        collection = self._ensure_collection()
        if collection is None or not query_text.strip():
            return []
        top_k = top_k or self.settings.rag_top_k
        try:
            result = collection.query(
                query_texts=[query_text],
                n_results=min(top_k + (1 if exclude_id else 0), max(collection.count(), 1)),
                where={"user_id": user_id},
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("向量检索失败: %s", exc)
            return []

        hits: list[RagHit] = []
        ids = (result.get("ids") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]
        documents = (result.get("documents") or [[]])[0]
        metadatas = (result.get("metadatas") or [[]])[0]
        for qid, dist, doc, meta in zip(ids, distances, documents, metadatas, strict=False):
            numeric_id = int(qid)
            if exclude_id is not None and numeric_id == exclude_id:
                continue
            hits.append(
                RagHit(
                    question_id=numeric_id,
                    distance=float(dist),
                    tags=[t for t in str(meta.get("tags", "")).split(",") if t],
                    snippet=(doc or "")[:200],
                )
            )
            if len(hits) >= top_k:
                break
        return hits
