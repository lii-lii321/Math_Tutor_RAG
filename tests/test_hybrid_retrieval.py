"""混合检索管线测试（Batch 01）：rerank 顺序、候选池、阈值、过滤、调试日志。

向量通道通过 monkeypatch 控制，聚焦管线编排逻辑本身。
"""
from __future__ import annotations

import json
import logging

import pytest

from backend.database import SessionLocal
from backend.models.orm import User
from backend.services.question_service import QuestionService
from backend.services.rag import RagHit


@pytest.fixture
def service():
    return QuestionService(session_factory=SessionLocal)


def _hit(qid: int, distance: float = 0.1) -> RagHit:
    return RagHit(question_id=qid, distance=distance)


def _patch_dense(monkeypatch, service, hits: list[RagHit], captured: list | None = None):
    def fake_dense(query, *, user_ids, candidate_k=None, min_similarity=None):
        if captured is not None:
            captured.append(
                {"query": query, "candidate_k": candidate_k, "min_similarity": min_similarity}
            )
        return hits

    monkeypatch.setattr(service.vector_store, "hybrid_dense_search", fake_dense)


def _patch_rerank(monkeypatch, order: list[int] | None = None, captured: list | None = None):
    def fake_rerank(query, docs, *, base_url, api_key, model, top_k):
        if captured is not None:
            captured.append({"docs": docs, "top_k": top_k})
        if order is None:
            return None
        return [(i, 1.0 - i / 10) for i in order]

    monkeypatch.setattr("backend.services.fusion.rerank", fake_rerank)


def _enable_rerank(service):
    service.settings.rerank_base_url = "https://api.example.com"
    service.settings.rerank_api_key = "k"


def test_hybrid_hydrates_vector_only_before_rerank(service, student_user, monkeypatch):
    """核心修复验证：reranker 必须看到完整候选集（含 vector-only 文档）。"""

    # 造两道题：一道关键词可命中，一道仅向量可召回
    kw_q = service.create_manual_question(
        student_user.id, content_markdown="判别式关键词命中题", tags=["方程"]
    )
    vec_q = service.create_manual_question(
        student_user.id, content_markdown="向量专属召回题：导数与单调性讨论", tags=["导数"]
    )
    # 关键词查询"判别式"只会命中第一题
    captured_rerank: list = []
    _patch_dense(
        monkeypatch, service, [_hit(vec_q.id, 0.05), _hit(kw_q.id, 0.5)]
    )
    _patch_rerank(monkeypatch, [0, 1], captured_rerank)
    _enable_rerank(service)

    results = service.list_questions(student_user.id, keyword="判别式")
    rerank_call = captured_rerank[0]
    # reranker 看到的 docs 必须同时包含两题（修复前只有关键词命中的 1 题）
    assert len(rerank_call["docs"]) >= 2
    ids_in_results = {q.id for q in results}
    assert {kw_q.id, vec_q.id} <= ids_in_results


def test_hybrid_rerank_reorders_final_results(service, student_user, monkeypatch):
    jia = service.create_manual_question(
        student_user.id, content_markdown="题目甲：判别式", tags=["方程"]
    )
    yi = service.create_manual_question(
        student_user.id, content_markdown="题目乙：判别式变式", tags=["方程"]
    )
    captured: list = []
    # dense 把乙排前（RRF 后乙第一）；rerank 交换为甲第一 → 验证重排真正生效
    _patch_dense(
        monkeypatch,
        service,
        [_hit(yi.id, 0.05), _hit(jia.id, 0.3)],
    )
    _patch_rerank(monkeypatch, order=[1, 0], captured=captured)
    _enable_rerank(service)

    results = service.list_questions(student_user.id, keyword="判别式")
    assert len(results) >= 2
    assert results[0].id == jia.id
    assert captured and captured[0]["top_k"] == service.settings.rag_top_k


def test_rerank_failure_falls_back_to_fusion_order(service, student_user, monkeypatch):
    service.create_manual_question(
        student_user.id, content_markdown="回退测试题", tags=["t"]
    )

    def _boom(query, docs, **kwargs):
        raise httpx_down()

    def httpx_down():
        raise ConnectionError("down")

    _patch_dense(monkeypatch, service, [])
    monkeypatch.setattr("backend.services.fusion.rerank", _boom)
    _enable_rerank(service)

    results = service.list_questions(student_user.id, keyword="回退测试题")
    assert any("回退测试题" in q.content_markdown for q in results)  # 不崩溃且结果正确


def test_min_similarity_filters_vector_only_hits(service, student_user, monkeypatch):
    kept = service.create_manual_question(
        student_user.id, content_markdown="高相似题", tags=["a"]
    )
    low = service.create_manual_question(
        student_user.id, content_markdown="低分噪声题", tags=["b"]
    )
    service.settings.rag_min_similarity = 0.5
    # 关键词"相似"只命中 kept；low 仅来自向量且 distance 0.9 → sim 0.1 < 0.5，应被过滤
    _patch_dense(
        monkeypatch, service, [_hit(kept.id, 0.1), _hit(low.id, 0.9)]
    )

    results = service.list_questions(student_user.id, keyword="相似")
    ids = {q.id for q in results}
    assert kept.id in ids
    assert low.id not in ids
    service.settings.rag_min_similarity = 0.0


def test_keyword_channel_uses_candidate_pool(service, student_user, monkeypatch):
    captured: list = []
    _patch_dense(monkeypatch, service, [], captured=captured)
    service.create_manual_question(
        student_user.id, content_markdown="候选池深度题", tags=["c"]
    )
    service.list_questions(student_user.id, keyword="候选池")
    assert captured and captured[0]["candidate_k"] == service.settings.rag_candidate_k


def test_no_keyword_returns_time_order(service, student_user):
    q1 = service.create_manual_question(student_user.id, content_markdown="先建")
    q2 = service.create_manual_question(student_user.id, content_markdown="后建")
    results = service.list_questions(student_user.id, semantic=True)
    ids = [q.id for q in results]
    assert ids.index(q2.id) < ids.index(q1.id)  # 时间倒序


def test_offset_limit_applied_on_hybrid_path(service, student_user, monkeypatch):
    for i in range(5):
        service.create_manual_question(
            student_user.id, content_markdown=f"分页题 {i} 判别式", tags=["p"]
        )
    _patch_dense(monkeypatch, service, [])
    page = service.list_questions(
        student_user.id, keyword="分页题", offset=1, limit=2
    )
    assert len(page) == 2


def test_debug_log_emits_pipeline_json(service, student_user, monkeypatch, caplog):
    service.create_manual_question(student_user.id, content_markdown="日志题 判别式", tags=["d"])
    service.settings.rag_debug_log = True
    _patch_dense(monkeypatch, service, [])
    with caplog.at_level(logging.INFO, logger="rag"):
        service.list_questions(student_user.id, keyword="判别式")
    service.settings.rag_debug_log = False

    pipeline_logs = [r for r in caplog.records if "rag_pipeline" in r.getMessage()]
    assert pipeline_logs
    payload = json.loads(pipeline_logs[-1].getMessage().split("rag_pipeline ", 1)[1])
    assert payload["query"] == "判别式"
    assert "latency_ms" in payload and "fused_ids" in payload


def test_debug_log_silent_when_disabled(service, student_user, monkeypatch, caplog):
    service.create_manual_question(student_user.id, content_markdown="静默题 判别式", tags=["d"])
    service.settings.rag_debug_log = False
    _patch_dense(monkeypatch, service, [])
    with caplog.at_level(logging.INFO, logger="rag"):
        service.list_questions(student_user.id, keyword="判别式")
    assert not [r for r in caplog.records if "rag_pipeline" in r.getMessage()]


def test_hybrid_excludes_other_users_vector_docs(service, student_user, db_session, monkeypatch):

    other = User(username="hybrid_other", password_hash="x", role="student")
    db_session.add(other)
    db_session.commit()
    other_q, _ = service.analyze_and_save(
        other.id, b"\xff\xd8" + b"o" * 16, user_tags=["他人"]
    )
    service.settings.rag_min_similarity = 0.0
    # 向量通道恶意/误配返回他人题 → hydrate 可见性过滤必须拦下
    _patch_dense(monkeypatch, service, [_hit(other_q.id, 0.05)])

    results = service.list_questions(student_user.id, keyword="任何词")
    assert all(q.id != other_q.id for q in results)


def test_difficulty_metadata_filter_on_keyword_path(service, student_user):
    service.create_manual_question(
        student_user.id,
        content_markdown="难度过滤题",
        tags=["f"],
        ai_analyze=False,
    )
    # create_manual_question 不带 difficulty，手动改一道为 hard
    from backend.database import SessionLocal
    from backend.models.orm import Question

    with SessionLocal() as session:
        q = (
            session.query(Question)
            .filter_by(user_id=student_user.id, content_markdown="难度过滤题")
            .first()
        )
        q.difficulty = "hard"
        session.commit()

    hard = service.list_questions(student_user.id, difficulty="hard")
    assert all(q.difficulty == "hard" for q in hard)
    assert any("难度过滤题" in q.content_markdown for q in hard)


def test_difficulty_filter_on_hybrid_path(service, student_user, monkeypatch):
    service.create_manual_question(
        student_user.id, content_markdown="混合难度过滤题 判别式", tags=["h"]
    )
    from backend.database import SessionLocal
    from backend.models.orm import Question

    with SessionLocal() as session:
        session.query(Question).filter_by(user_id=student_user.id).update(
            {"difficulty": "hard"}
        )
        session.commit()

    _patch_dense(monkeypatch, service, [])
    results = service.list_questions(
        student_user.id, keyword="判别式", difficulty="easy"
    )
    assert all(q.difficulty == "easy" for q in results)
    assert not any("混合难度过滤题" in q.content_markdown for q in results)


def test_rag_disabled_still_keyword_searchable(service, student_user, monkeypatch):
    service.settings.rag_enabled = False
    service.vector_store._available = None  # 强制重新探测
    service.create_manual_question(
        student_user.id, content_markdown="禁用向量后的关键词题", tags=["x"]
    )
    results = service.list_questions(student_user.id, keyword="禁用向量")
    assert any("禁用向量" in q.content_markdown for q in results)
    service.settings.rag_enabled = True
    service.vector_store._available = None


def test_semantic_false_skips_vector_channel(service, student_user, monkeypatch):
    called: list = []
    _patch_dense(monkeypatch, service, [], captured=called)
    service.create_manual_question(student_user.id, content_markdown="纯关键词题", tags=["y"])
    results = service.list_questions(
        student_user.id, keyword="纯关键词", semantic=False
    )
    assert called == []  # 未触碰向量通道
    assert any("纯关键词" in q.content_markdown for q in results)


def test_empty_keyword_lists_all(service, student_user, monkeypatch):
    service.create_manual_question(student_user.id, content_markdown="空关键词题", tags=["z"])
    results = service.list_questions(student_user.id, keyword=None)
    assert any("空关键词题" in q.content_markdown for q in results)
