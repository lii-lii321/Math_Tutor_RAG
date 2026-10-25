"""嵌入身份指纹与向量删除韧性测试（提升项 #11/#17）。"""
from __future__ import annotations

import os
from pathlib import Path

from backend.config import Settings
from backend.services.rag import (
    EMBEDDING_META_KEY,
    QuestionVectorStore,
    embedding_fingerprint,
)


def _local_settings() -> Settings:
    settings = Settings()
    settings.rag_enabled = True
    return settings


def _remote_settings(base_url: str = "https://embed.example.com/v1") -> Settings:
    # 密钥用运行时随机值：指纹只由 base_url|model 决定，占位密钥不构成凭据
    return Settings(
        embedding_base_url=base_url,
        embedding_api_key=os.urandom(8).hex(),
        embedding_model="BAAI/bge-m3",
        chroma_dir=Settings().chroma_dir,
        rag_enabled=True,
    )


def test_fingerprint_distinguishes_local_and_remote():
    assert embedding_fingerprint(_local_settings()) == "chromadb-default"
    remote = embedding_fingerprint(_remote_settings())
    assert remote == "https://embed.example.com/v1|BAAI/bge-m3"
    assert remote != "chromadb-default"


def test_collection_records_fingerprint_on_create(tmp_path):
    settings = Settings()
    settings.chroma_dir = Path(tmp_path) / "chroma_fp"
    store = QuestionVectorStore(settings)
    store.upsert_question(990001, "指纹测试题", user_id=990001, tags=["测试"])
    status = store.embedding_status()
    assert status["stored"] == "chromadb-default"
    assert status["match"] is True
    assert status.get("legacy") is False


def test_mismatch_detected_when_model_switched(tmp_path):
    """同一 chroma 目录先本地建库，再以远程嵌入配置打开：必须报 mismatch。

    函数级冲突（default↔openai）下 chroma 挂载即抛错降级关键词——
    指纹探测发生在挂载前（bare get_collection），降级也能报出 mismatch。
    """
    local = Settings()
    local.chroma_dir = Path(tmp_path) / "chroma_mix"
    store_local = QuestionVectorStore(local)
    store_local.upsert_question(990002, "本地嵌入题", user_id=990002, tags=["测试"])

    remote = _remote_settings()
    remote.chroma_dir = local.chroma_dir
    store_remote = QuestionVectorStore(remote)
    status = store_remote.embedding_status()
    assert status["mismatch"] is True
    assert status["match"] is False
    assert status["stored"] == "chromadb-default"
    assert status["current"].startswith("https://embed.example.com")
    assert status["vector_available"] is False  # 函数冲突 → 降级关键词，但身份已识别


def test_legacy_collection_without_fingerprint_is_flagged(tmp_path):
    """旧集合（无指纹键）不误报 mismatch，标记 legacy 供体检提示重建。"""
    local = Settings()
    local.chroma_dir = Path(tmp_path) / "chroma_legacy"
    store = QuestionVectorStore(local)
    store.upsert_question(990003, "旧集合题", user_id=990003, tags=["测试"])
    # 模拟旧集合：metadata 整体替换为不含指纹键的字典（不带 hnsw:space，
    # chromadb 的 modify 校验拒绝显式改动 distance 配置键）
    store._collection.modify(metadata={"note": "legacy-sim"})
    fresh = QuestionVectorStore(local)  # 重新探测
    status = fresh.embedding_status()
    assert status["legacy"] is True
    assert status["mismatch"] is None
    assert status["match"] is False
    assert EMBEDDING_META_KEY not in (status["stored"] or "")


def test_empty_user_scope_fails_closed(tmp_path, monkeypatch):
    """空可见范围失败关闭（外审 2026-10-25 P0-2）：返回空且绝不触达 collection。

    修复前 user_ids=[] 会把 where 置 None——退化成无用户过滤的全库查询。
    """
    local = Settings()
    local.chroma_dir = Path(tmp_path) / "chroma_failclosed"
    store = QuestionVectorStore(local)
    store.upsert_question(990005, "失败关闭探针题", user_id=990005, tags=["测试"])

    class _NoQueryAllowed:
        def query(self, *args, **kwargs):  # pragma: no cover - 触达即失败
            raise AssertionError("空用户范围不得触达 collection.query")

    monkeypatch.setattr(store, "_collection", _NoQueryAllowed())
    assert store.semantic_search("探针", user_ids=[], top_k=5) == []
    assert store.similar_questions("探针", user_ids=[], top_k=5) == []
    assert store.hybrid_dense_search("探针", user_ids=[]) == []


def test_delete_retries_once_on_transient_failure(tmp_path, monkeypatch):
    """删除首败重试成功不告警；两败才记录遥测。"""
    local = Settings()
    local.chroma_dir = Path(tmp_path) / "chroma_retry"
    store = QuestionVectorStore(local)
    store.upsert_question(990004, "重试题", user_id=990004, tags=["测试"])

    calls: list[int] = []

    class _FlakyDelete:
        def __init__(self, real):
            self._real = real

        def __call__(self, ids):
            calls.append(len(ids))
            if len(calls) == 1:
                raise RuntimeError("transient chroma hiccup")
            return self._real(ids=ids)

    monkeypatch.setattr(
        store._collection, "delete", _FlakyDelete(store._collection.delete)
    )
    store.delete_questions([990004])
    assert len(calls) == 2  # 重试后成功
    assert 990004 not in store.indexed_ids_for_user(990004)
