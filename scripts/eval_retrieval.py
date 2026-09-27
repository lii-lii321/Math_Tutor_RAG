"""检索评测：量化 RRF 混合检索相对单路检索的召回提升（Recall@K）。

方法：以错题自身解析中的关键词为查询，检验目标题是否出现在 top-K。
对比三路：仅关键词（SQL LIKE）/ 仅向量 / RRF 融合。

运行（需先 init_db + 有若干错题）：
    python -m scripts.eval_retrieval
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


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

    k_values = (1, 3, 5, 10)
    recall = {
        "keyword": {k: 0 for k in k_values},
        "vector": {k: 0 for k in k_values},
        "rrf": {k: 0 for k in k_values},
    }
    mrr = {"keyword": 0.0, "vector": 0.0, "rrf": 0.0}
    ndcg = {"keyword": 0.0, "vector": 0.0, "rrf": 0.0}
    latencies = {"keyword": [], "vector": [], "rrf": []}
    total = 0

    def mrr_at(ranked: list[int], target: int) -> float:
        for rank, qid in enumerate(ranked, 1):
            if qid == target:
                return 1.0 / rank
        return 0.0

    def ndcg_at(ranked: list[int], target: int, k: int) -> float:
        for rank, qid in enumerate(ranked[:k], 1):
            if qid == target:
                return 1.0 / __import__("math").log2(rank + 1)
        return 0.0

    for q in questions:
        # 用该题标签构造查询（模拟真实用户检索词）
        query = (q.tags or [""])[0] if q.tags else None
        if not query:
            continue
        total += 1

        t0 = time.perf_counter()
        kw_ids = keyword_rank(query)
        latencies["keyword"].append((time.perf_counter() - t0) * 1000)

        t0 = time.perf_counter()
        vec_ids = vector_rank(query)
        latencies["vector"].append((time.perf_counter() - t0) * 1000)

        t0 = time.perf_counter()
        fused = rrf_fuse(vec_ids, kw_ids, top_k=10)
        latencies["rrf"].append((time.perf_counter() - t0) * 1000)

        for k in k_values:
            if q.id in kw_ids[:k]:
                recall["keyword"][k] += 1
            if q.id in vec_ids[:k]:
                recall["vector"][k] += 1
            if q.id in fused[:k]:
                recall["rrf"][k] += 1

        mrr["keyword"] += mrr_at(kw_ids, q.id)
        mrr["vector"] += mrr_at(vec_ids, q.id)
        mrr["rrf"] += mrr_at(fused, q.id)
        ndcg["keyword"] += ndcg_at(kw_ids, q.id, 10)
        ndcg["vector"] += ndcg_at(vec_ids, q.id, 10)
        ndcg["rrf"] += ndcg_at(fused, q.id, 10)

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

    print(f"\nMRR（越高越好）：关键词 {mrr['keyword'] / total:.3f} | "
          f"向量 {mrr['vector'] / total:.3f} | RRF {mrr['rrf'] / total:.3f}")
    print(f"NDCG@10：关键词 {ndcg['keyword'] / total:.3f} | "
          f"向量 {ndcg['vector'] / total:.3f} | RRF {ndcg['rrf'] / total:.3f}")
    print(f"P50 延迟 ms：关键词 {sorted(latencies['keyword'])[total // 2]:.0f} | "
          f"向量 {sorted(latencies['vector'])[total // 2]:.0f} | "
          f"RRF {sorted(latencies['rrf'])[total // 2]:.0f}")

    # JSON 报告（供 CI/回归对比）
    report = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "samples": total,
        "pipelines": {},
    }
    for name in ("keyword", "vector", "rrf"):
        report["pipelines"][name] = {
            f"recall_at_{k}": round(recall[name][k] / total, 3) for k in k_values
        }
        report["pipelines"][name]["mrr"] = round(mrr[name] / total, 3)
        report["pipelines"][name]["ndcg_at_10"] = round(ndcg[name] / total, 3)
        report["pipelines"][name]["latency_p50_ms"] = round(
            sorted(latencies[name])[total // 2]
        )
    out = Path(__file__).resolve().parents[1] / "data" / "eval_report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nJSON 报告已写入：{out}")


if __name__ == "__main__":
    main()
