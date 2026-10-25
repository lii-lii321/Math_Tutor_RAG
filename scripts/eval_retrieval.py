"""检索评测：量化 RRF 混合检索相对单路检索的召回提升（Recall@K）。

方法：以错题自身解析中的关键词为查询，检验目标题是否出现在 top-K。
对比三路：仅关键词（SQL LIKE）/ 仅向量 / RRF 融合。

提升项 #9：默认组查询 = 题目标签，天然利好关键词路（标签必然出现在
被命中文本里）；--golden 组改用金标集的语义改写问法（学生口语句，
与原题表述不同），衡量真实的语义召回——这才是嵌入/reranker 实验
该看的数字。两组分开报告，不混口径。

运行（需先 init_db + 有若干错题）：
    python -m scripts.eval_retrieval            # 标签查询组（历史口径）
    python -m scripts.eval_retrieval --golden   # 语义改写组（金标语料）
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _load_golden() -> list[tuple[str, list[str], str, str]]:
    """从检索金标测试文件加载 (内容, 标签, 关键词查询, 语义查询)。importlib 直载，
    不经 pytest 收集——语料是单一事实源，评测与门禁不各养一份。"""
    import importlib.util

    path = Path(__file__).resolve().parents[1] / "tests" / "test_retrieval_quality.py"
    spec = importlib.util.spec_from_file_location("mm_golden_corpus", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return [
        (content, list(tags), kw, sem)
        for content, tags, kw, sem in module._GOLDEN
    ]


def _golden_group(store, user_id: int, entries) -> dict:
    """语义改写组：金标语料（专属用户隔离）× 语义问法，三路对比。"""
    from backend.database import SessionLocal
    from backend.repositories.questions import QuestionRepository
    from backend.services.fusion import rrf_fuse

    with SessionLocal() as session:
        questions = QuestionRepository(session).list_for_user(user_id)
    by_content = {q.content_markdown: q for q in questions}

    k_values = (1, 3, 5, 10)
    recall = {name: {k: 0 for k in k_values} for name in ("keyword", "vector", "rrf")}
    mrr = {"keyword": 0.0, "vector": 0.0, "rrf": 0.0}
    latencies = {"keyword": [], "vector": [], "rrf": []}
    total = 0

    for content, _tags, _kw, sem in entries:
        target = by_content.get(content)
        if target is None:
            continue  # 语料缺失（未跑过金标测试）时跳过该条
        total += 1

        t0 = time.perf_counter()
        kw_ids = [q.id for q in questions if sem in q.content_markdown]
        latencies["keyword"].append((time.perf_counter() - t0) * 1000)

        t0 = time.perf_counter()
        vec_ids = [h.question_id for h in store.semantic_search(sem, user_ids=[user_id], top_k=10)]
        latencies["vector"].append((time.perf_counter() - t0) * 1000)

        t0 = time.perf_counter()
        fused = rrf_fuse(vec_ids, kw_ids, top_k=10)
        latencies["rrf"].append((time.perf_counter() - t0) * 1000)

        for k in k_values:
            for name, ids in (("keyword", kw_ids), ("vector", vec_ids), ("rrf", fused)):
                if target.id in ids[:k]:
                    recall[name][k] += 1
        for name, ids in (("keyword", kw_ids), ("vector", vec_ids), ("rrf", fused)):
            for rank, qid in enumerate(ids, 1):
                if qid == target.id:
                    mrr[name] += 1.0 / rank
                    break

    if total == 0:
        print("金标用户无语料——先跑一次 tests/test_retrieval_quality.py 播种语料")
        return {"samples": 0}

    def _pipeline(name: str) -> dict:
        return {
            f"recall_at_{k}": round(recall[name][k] / total, 3) for k in k_values
        } | {
            "mrr": round(mrr[name] / total, 3),
            "latency_p50_ms": round(sorted(latencies[name])[total // 2]),
        }

    return {"samples": total, "pipelines": {n: _pipeline(n) for n in ("keyword", "vector", "rrf")}}


def main() -> None:
    os.environ.setdefault("AI_PROVIDER", "mock")
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--golden", action="store_true", help="跑语义改写组（金标语料）")
    args = parser.parse_args()

    from backend.config import get_settings
    from backend.database import SessionLocal, init_db
    from backend.models.orm import User
    from backend.repositories.questions import QuestionRepository
    from backend.services.fusion import rrf_fuse
    from backend.services.rag import QuestionVectorStore

    init_db(seed_users=True)
    settings = get_settings()
    store = QuestionVectorStore(settings)

    report: dict = {"generated_at": dt.datetime.now(dt.timezone.utc).isoformat()}

    if args.golden:
        entries = _load_golden()
        with SessionLocal() as session:
            golden_user = session.query(User).filter_by(username="golden_retrieval").first()
        from backend.services.question_service import QuestionService

        q_service = QuestionService(session_factory=SessionLocal)
        if golden_user is None:
            # 自播种（幂等）：金标语料进专属用户，与测试门禁同一份语料源
            import secrets

            from backend.services.auth import AuthService, RegisterInput

            with SessionLocal() as session:
                result = AuthService(session).register(
                    RegisterInput(
                        username="golden_retrieval",
                        password=secrets.token_hex(8),
                        role="student",
                    )
                )
                session.commit()
                golden_user = session.get(User, result.user_id)
        existing_contents = {
            q.content_markdown for q in q_service.list_questions(golden_user.id, semantic=False)
        }
        missing = [
            (content, tags) for content, tags, _kw, _sem in entries
            if content not in existing_contents
        ]
        for content, tags in missing:
            q_service.create_manual_question(
                golden_user.id, content_markdown=content, tags=list(tags)
            )
        if missing:
            print(f"已播种金标语料 {len(missing)} 条（用户 golden_retrieval）")
        group = _golden_group(store, golden_user.id, entries)
        report["semantic_group"] = group
        if group.get("samples"):
            print(f"语义改写组（{group['samples']} 条金标问法）：")
            for name, metrics in group["pipelines"].items():
                print(
                    f"  {name:>8}: R@3={metrics['recall_at_3']} "
                    f"R@10={metrics['recall_at_10']} MRR={metrics['mrr']}"
                )
    else:
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

        print(f"标签查询组（历史口径，{total} 条）· Recall@K（越高越好）")
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

        report["tag_group"] = {
            "samples": total,
            "pipelines": {},
        }
        for name in ("keyword", "vector", "rrf"):
            report["tag_group"]["pipelines"][name] = {
                f"recall_at_{k}": round(recall[name][k] / total, 3) for k in k_values
            }
            report["tag_group"]["pipelines"][name]["mrr"] = round(mrr[name] / total, 3)
            report["tag_group"]["pipelines"][name]["ndcg_at_10"] = round(ndcg[name] / total, 3)
            report["tag_group"]["pipelines"][name]["latency_p50_ms"] = round(
                sorted(latencies[name])[total // 2]
            )

    out = Path(__file__).resolve().parents[1] / "data" / "eval_report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nJSON 报告已写入：{out}")


if __name__ == "__main__":
    main()
