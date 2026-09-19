"""混合检索融合：Reciprocal Rank Fusion（RRF）+ 可选重排钩子。

RRF 是无参融合方法：score(d) = Σ 1/(k + rank_i(d))，k 取 60 为业界常用值。
纯函数实现，便于单测；重排为可选 HTTP 调用（未配置时直通融合结果）。
"""
from __future__ import annotations

import httpx

from backend.utils.logging import get_logger

logger = get_logger("rerank")

RRF_K = 60


def rrf_fuse(*ranked_id_lists: list[int], top_k: int = 10) -> list[int]:
    """融合多路排序列表，返回去重后的融合排序 ID。

    >>> rrf_fuse([1, 2, 3], [3, 1], top_k=3)
    [1, 3, 2]
    """
    scores: dict[int, float] = {}
    for ids in ranked_id_lists:
        for rank, qid in enumerate(ids):
            scores[qid] = scores.get(qid, 0.0) + 1.0 / (RRF_K + rank + 1)
    ordered = sorted(scores, key=lambda qid: scores[qid], reverse=True)
    return ordered[:top_k]


def rerank(
    query: str, documents: list[str], *, base_url: str, api_key: str, model: str, top_k: int
) -> list[tuple[int, float]] | None:
    """调用 OpenAI 兼容 rerank 接口（如 SiliconFlow /v1/rerank, BAAI/bge-reranker-v2-m3）。

    返回 [(原文档索引, 相关性分数)] 按分数降序；未配置或失败时返回 None（调用方直通）。
    """
    if not base_url or not api_key:
        return None
    try:
        resp = httpx.post(
            f"{base_url.rstrip('/')}/rerank",
            headers={"Authorization": f"Bearer {api_key}"},
            json={"model": model, "query": query, "documents": documents, "top_n": top_k},
            timeout=15,
        )
        resp.raise_for_status()
        results = resp.json().get("results", [])
        return [(int(item["index"]), float(item["relevance_score"])) for item in results]
    except Exception as exc:  # noqa: BLE001 - 重排失败不阻断检索主流程
        logger.warning("重排调用失败，使用融合排序: %s", exc)
        return None
