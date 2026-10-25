"""RAG 服务：基于 ChromaDB 的错题向量库。

能力：
1. 错题解析文本入库（含知识点/标签元数据）
2. 「举一反三」相似题召回
3. 错题本语义搜索（自然语言找题，不依赖标签完全匹配）

嵌入模型策略：
- 配置了 EMBEDDING_BASE_URL/KEY → 使用 OpenAI 兼容嵌入接口（如 BGE-M3）
- 未配置 → 使用 ChromaDB 内置本地嵌入模型，零外部依赖

任何环节故障均自动降级为关键词检索，保证主流程不被向量库阻断。

嵌入身份指纹：collection metadata 记录建库时的嵌入模型标识；
切换嵌入模型后旧向量与新查询不同空间，检索质量会静默劣化——
ensure 时比对并在 data_health 体检中显式暴露（提示重建索引）。
"""
from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass, field

from backend.config import Settings, get_settings
from backend.utils.logging import get_logger

logger = get_logger("rag")

# collection metadata 中记录嵌入身份的键
EMBEDDING_META_KEY = "mm:embedding"


def embedding_fingerprint(settings: Settings) -> str:
    """当前配置的嵌入身份：远程 (base_url|model) 或本地内置。"""
    if settings.embedding_base_url and settings.embedding_api_key:
        return f"{settings.embedding_base_url.rstrip('/')}|{settings.embedding_model}"
    return "chromadb-default"


@dataclass
class RagHit:
    question_id: int
    distance: float
    tags: list[str] = field(default_factory=list)
    snippet: str = ""


@dataclass
class SearchResult:
    """统一检索结果：上层不接触 ChromaDB 原始结构。"""

    question_id: int
    score: float  # 相似度（1 - cosine distance），越高越相关
    source: str  # "dense" | "keyword" | "hybrid"
    rank: int


def _similarity(distance: float) -> float:
    """cosine 距离 → 相似度（0~1，越高越相关）。"""
    return max(0.0, min(1.0, 1.0 - distance))


def _log_pipeline(debug_enabled: bool, **payload) -> None:
    """RAG 管线调试日志：query/各路结果/融合/重排/延迟一次记录。"""
    if debug_enabled:
        logger.info("rag_pipeline %s", json.dumps(payload, ensure_ascii=False, default=str))


class QuestionVectorStore:
    """ChromaDB 持久化向量库的轻量封装。"""

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self._collection = None
        self._available: bool | None = None  # None = 未探测
        self._stored_fingerprint: str | None = None  # 建库时记录的嵌入身份
        self._embedding_mismatch: bool | None = None  # None = 未探测/旧集合无指纹

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
            fingerprint = embedding_fingerprint(self.settings)
            # 先取 bare 集合（不带 embedding_function）探测建库时的嵌入身份：
            # chroma 对函数级冲突（default vs openai）会在挂载时直接抛错降级，
            # 模型级切换（两个远程模型）则静默混用——两者都要在降级/挂载前显式识别
            try:
                self._check_embedding_fingerprint(
                    (client.get_collection(name="questions").metadata or {}),
                    fingerprint,
                )
            except Exception:  # noqa: BLE001 - 集合尚不存在：首次建库
                self._stored_fingerprint = None
                self._embedding_mismatch = None
            self._collection = client.get_or_create_collection(
                name="questions",
                embedding_function=embed_fn,
                metadata={
                    "hnsw:space": "cosine",
                    EMBEDDING_META_KEY: fingerprint,
                },
            )
            # 首次建库：bare 探测时集合尚不存在，挂载后回读补齐指纹；
            # 旧集合（无指纹键）回读仍为 None → 保持 legacy 语义
            if self._stored_fingerprint is None:
                try:
                    stored_back = (self._collection.metadata or {}).get(EMBEDDING_META_KEY)
                except Exception:  # noqa: BLE001 - 测试替身等无 metadata 属性
                    stored_back = None
                self._stored_fingerprint = stored_back
                self._embedding_mismatch = (
                    None if stored_back is None else stored_back != fingerprint
                )
            self._available = True
        except Exception as exc:  # noqa: BLE001 - 向量库故障不阻断主流程
            logger.warning("向量库初始化失败，已降级为关键词检索: %s", exc)
            self._collection = None
            self._available = False
        return self._collection

    def _check_embedding_fingerprint(self, stored_metadata: dict, current: str) -> None:
        """比对集合内记录的嵌入身份：不一致即告警（检索空间已换，需重建索引）。"""
        stored = stored_metadata.get(EMBEDDING_META_KEY)
        self._stored_fingerprint = stored
        if stored is None:
            self._embedding_mismatch = None
            logger.info(
                "向量集合缺少嵌入身份指纹（旧集合）——建议用 data_health 重建索引以补录"
            )
            return
        self._embedding_mismatch = stored != current
        if self._embedding_mismatch:
            logger.warning(
                "嵌入模型与建库时不一致（建库=%s 当前=%s）——旧向量与新查询"
                "不在同一空间，检索质量已劣化，请用数据体检重建索引",
                stored,
                current,
            )

    def embedding_status(self) -> dict:
        """嵌入身份健康信息（data_health 体检用）；未启用 RAG 时 match=None。"""
        if self._available is None:
            self._ensure_collection()
        return {
            "current": embedding_fingerprint(self.settings),
            "stored": self._stored_fingerprint,
            "match": self._stored_fingerprint is not None
            and self._embedding_mismatch is False,
            "mismatch": self._embedding_mismatch,
            "legacy": self._stored_fingerprint is None,
            "vector_available": bool(self._available),
        }

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
        # 失败重试一次：残留索引靠 data_health 体检兜底，但先自救降低漂移概率
        for attempt in (1, 2):
            try:
                collection.delete(ids=[str(qid) for qid in question_ids])
                return
            except Exception as exc:  # noqa: BLE001
                if attempt == 2:
                    from backend.services.ai.telemetry import record_event

                    logger.warning(
                        "向量删除失败（已重试，残留索引待数据体检清理）: %s", exc
                    )
                    record_event(
                        "rag_delete_failed",
                        question_ids=",".join(str(q) for q in question_ids[:20]),
                        error=f"{type(exc).__name__}: {exc}",
                    )

    def indexed_ids_for_user(self, user_id: int) -> set[int]:
        """该用户已建立向量索引的题目 ID 集（数据体检用）。"""
        collection = self._ensure_collection()
        if collection is None:
            return set()
        try:
            try:
                rows = collection.get(where={"user_id": {"$eq": user_id}}, include=[])
            except (TypeError, ValueError):  # 旧版 chroma 不接受空 include
                rows = collection.get(where={"user_id": {"$eq": user_id}})
            return {int(rid) for rid in rows.get("ids", []) if str(rid).isdigit()}
        except Exception as exc:  # noqa: BLE001
            logger.warning("向量索引枚举失败: %s", exc)
            return set()

    # ---------- 检索 ----------
    def similar_questions(
        self,
        query_text: str,
        *,
        user_ids: list[int],
        exclude_id: int | None = None,
        top_k: int | None = None,
    ) -> list[RagHit]:
        return self._query(query_text, user_ids=user_ids, exclude_id=exclude_id, top_k=top_k)

    def semantic_search(
        self,
        query: str,
        *,
        user_ids: list[int],
        top_k: int | None = None,
        min_similarity: float | None = None,
    ) -> list[RagHit]:
        """向量检索：支持候选池深度与相似度阈值过滤。"""
        hits = self._query(query, user_ids=user_ids, exclude_id=None, top_k=top_k)
        threshold = self.settings.rag_min_similarity if min_similarity is None else min_similarity
        if threshold > 0:
            hits = [h for h in hits if _similarity(h.distance) >= threshold]
        return hits

    def hybrid_dense_search(
        self,
        query: str,
        *,
        user_ids: list[int],
        candidate_k: int | None = None,
        min_similarity: float | None = None,
    ) -> list[RagHit]:
        """深候选池向量检索（融合前取 Dense Top candidate_k，而非最终 top_k）。"""
        return self.semantic_search(
            query,
            user_ids=user_ids,
            top_k=candidate_k or self.settings.rag_candidate_k,
            min_similarity=min_similarity,
        )

    def _query(
        self,
        query_text: str,
        *,
        user_ids: list[int],
        exclude_id: int | None,
        top_k: int | None,
    ) -> list[RagHit]:
        collection = self._ensure_collection()
        if collection is None or not query_text.strip():
            return []
        top_k = top_k or self.settings.rag_top_k
        where = {"user_id": {"$in": user_ids}} if user_ids else None
        try:
            # where 过滤由 chromadb 在查询时执行，无需先 count
            result = collection.query(
                query_texts=[query_text],
                n_results=top_k + (1 if exclude_id else 0),
                where=where,
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
