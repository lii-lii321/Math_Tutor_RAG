"""检索评测：量化 RRF 混合检索相对单路检索的召回提升（Recall@K）。

方法：以错题自身解析中的关键词为查询，检验目标题是否出现在 top-K。
对比三路：仅关键词（SQL LIKE）/ 仅向量 / RRF 融合。

运行（需先 init_db + 有若干错题）：
    python -m scripts.eval_retrieval
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import os  # noqa: E402


def main() -> None:
    os.environ.setdefault("AI_PROVIDER", "mock")
    from backend.config import get_settings
    from backend.database import SessionLocal, init_db
    from backend.models.orm import User
    from backend.repositories.questions import QuestionRepository
    from backend.services.fusion import rrf_fuse
    from backend.services.rag import QuestionVectorStore

    init_db(seed_users=True)
    settings = get_settings()
    store = QuestionVectorStore(settings)

    with SessionLocal() as session:
        user = session.query(User).filter_by(username="demo").first()
        if user is None:
            print("无 demo 用户，请先运行应用初始化")
            return
        repo = QuestionRepository(session)
        questions = repo.list_for_user(user.id)
        if len(questions) < 3:
            print(f"错题太少（{len(questions)}），先录入更多数据再评测")
            return

    def keyword_rank(query: str) -> list[int]:
        kw = query.lower()
        hits = [
            q
            for q in questions
            if kw in (q.content_markdown or "").lower()
            or kw in (q.answer or "").lower()
            or kw in (q.ocr_text or "").lower()
            or any(kw in str(t).lower() for t in (q.tags or []))
        ]
        return [q.id for q in hits]

    def vector_rank(query: str) -> list[int]:
        hits = store.semantic_search(query, user_ids=[user.id], top_k=10)
        return [h.question_id for h in hits]

    k_values = (1, 3, 5)
    recall = {"keyword": {k: 0 for k in k_values}, "vector": {k: 0 for k in k_values}, "rrf": {k: 0 for k in k_values}}
    total = 0

    for q in questions:
        # 用该题标签构造查询（模拟真实用户检索词）
        query = (q.tags or [""])[0] if q.tags else None
        if not query:
            continue
        total += 1
        kw_ids = keyword_rank(query)
        vec_ids = vector_rank(query)
        fused = rrf_fuse(vec_ids, kw_ids, top_k=10)

        for k in k_values:
            if q.id in kw_ids[:k]:
                recall["keyword"][k] += 1
            if q.id in vec_ids[:k]:
                recall["vector"][k] += 1
            if q.id in fused[:k]:
                recall["rrf"][k] += 1

    if total == 0:
        print("无可评测样本（错题均无标签）")
        return

    print(f"评测样本：{total} 条查询 · Recall@K（越高越好）")
    print(f"{'K':>3} | {'关键词':>8} | {'向量':>8} | {'RRF融合':>8}")
    print("-" * 40)
    for k in k_values:
        kw_pct = round(recall["keyword"][k] / total * 100)
        vec_pct = round(recall["vector"][k] / total * 100)
        rrf_pct = round(recall["rrf"][k] / total * 100)
        print(f"{k:>3} | {kw_pct:>7}% | {vec_pct:>7}% | {rrf_pct:>7}%")


if __name__ == "__main__":
    main()
