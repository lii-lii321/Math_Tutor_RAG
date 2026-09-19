"""混合检索：RRF 融合与重排钩子测试。"""
from __future__ import annotations

import httpx

from backend.services.fusion import rerank, rrf_fuse


def test_rrf_basic_fusion():
    # 两路都把 1 排前 → 1 分最高；3 只出现在两路 → 融合后居中
    fused = rrf_fuse([1, 2, 3], [3, 1], top_k=5)
    assert fused[0] == 1
    assert set(fused) == {1, 2, 3}


def test_rrf_dedup_and_topk():
    fused = rrf_fuse([1, 2, 3, 4], [4, 5], top_k=3)
    assert len(fused) == 3
    assert fused[0] in (1, 4)  # 两路第一名融合后领先


def test_rrf_empty_lists():
    assert rrf_fuse([], [], top_k=5) == []
    assert rrf_fuse([1], [], top_k=1) == [1]


def test_rerank_returns_none_without_config():
    assert rerank("q", ["d"], base_url="", api_key="", model="m", top_k=5) is None


def test_rerank_parses_response(monkeypatch):
    class _Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"results": [{"index": 1, "relevance_score": 0.9}, {"index": 0, "relevance_score": 0.4}]}

    captured = {}

    def _fake_post(url, **kwargs):
        captured["url"] = url
        captured["json"] = kwargs.get("json")
        return _Resp()

    monkeypatch.setattr(httpx, "post", _fake_post)
    result = rerank(
        "判别式",
        ["文档零", "文档一"],
        base_url="https://api.example.com/v1",
        api_key="sk-x",
        model="reranker",
        top_k=2,
    )
    assert result == [(1, 0.9), (0, 0.4)]
    assert captured["url"].endswith("/rerank")
    assert captured["json"]["query"] == "判别式"


def test_rerank_failure_returns_none(monkeypatch):
    def _boom(**kwargs):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(httpx, "post", _boom)
    result = rerank(
        "q", ["d"], base_url="https://api.example.com", api_key="k", model="m", top_k=5
    )
    assert result is None  # 降级为直通融合
