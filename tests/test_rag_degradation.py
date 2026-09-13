"""RAG 向量库的降级路径与检索行为测试（全 mock，不出网）。"""
from __future__ import annotations

import sys
import types

import pytest

from backend.config import Settings
from backend.services.rag import QuestionVectorStore


def _rag_settings(tmp_path, remote_embedding: bool = False) -> Settings:
    return Settings(
        rag_enabled=True,
        chroma_dir=tmp_path / "chroma",
        embedding_base_url="https://emb.example/v1" if remote_embedding else "",
        embedding_api_key="emb-key" if remote_embedding else "",
        embedding_model="BAAI/bge-m3",
        rag_top_k=2,
        _env_file=None,  # type: ignore[call-arg]
    )


@pytest.fixture
def fake_chromadb(monkeypatch):
    """注入假 chromadb 模块，记录调用并返回可控的假集合。"""
    module = types.ModuleType("chromadb")
    utils = types.ModuleType("chromadb.utils")
    ef = types.ModuleType("chromadb.utils.embedding_functions")

    state: dict = {"client_error": None, "collections": {}}

    class _FakeCollection:
        def __init__(self, name: str):
            self.name = name
            self.upserts: list[dict] = []
            self.deleted: list[list[str]] = []
            self.query_result: dict = {"ids": [[]], "distances": [[]], "documents": [[]], "metadatas": [[]]}
            self._count = 5

        def count(self, where=None):
            return self._count

        def upsert(self, **kwargs):
            self.upserts.append(kwargs)

        def delete(self, ids):
            self.deleted.append(ids)

        def query(self, query_texts, n_results, where):
            assert query_texts and n_results >= 1
            return self.query_result

    class _FakeClient:
        def __init__(self, path):
            state["path"] = path

        def get_or_create_collection(self, name, embedding_function=None, metadata=None):
            state["embedding_fn"] = embedding_function
            state["metadata"] = metadata
            if state["client_error"]:
                raise state["client_error"]
            return state["collections"].setdefault(name, _FakeCollection(name))

    module.PersistentClient = _FakeClient

    class _DefaultEF:
        def __init__(self):
            self.kind = "default"

    class _OpenAIEF:
        def __init__(self, **kwargs):
            self.kind = "openai"
            state["openai_ef_kwargs"] = kwargs

    ef.DefaultEmbeddingFunction = _DefaultEF
    ef.OpenAIEmbeddingFunction = _OpenAIEF
    utils.embedding_functions = ef
    module.utils = utils
    monkeypatch.setitem(sys.modules, "chromadb", module)
    monkeypatch.setitem(sys.modules, "chromadb.utils", utils)
    monkeypatch.setitem(sys.modules, "chromadb.utils.embedding_functions", ef)
    return state


def test_ensure_collection_uses_local_embedding(tmp_path, fake_chromadb):
    store = QuestionVectorStore(_rag_settings(tmp_path))
    assert store.is_available() is True
    assert fake_chromadb["embedding_fn"].kind == "default"
    assert fake_chromadb["metadata"] == {"hnsw:space": "cosine"}


def test_remote_embedding_function_selected(tmp_path, fake_chromadb):
    store = QuestionVectorStore(_rag_settings(tmp_path, remote_embedding=True))
    assert store.is_available() is True
    assert fake_chromadb["embedding_fn"].kind == "openai"
    assert fake_chromadb["openai_ef_kwargs"]["model_name"] == "BAAI/bge-m3"
    assert fake_chromadb["openai_ef_kwargs"]["api_base"] == "https://emb.example/v1"


def test_client_failure_degrades_gracefully(tmp_path, fake_chromadb):
    fake_chromadb["client_error"] = RuntimeError("boom")
    store = QuestionVectorStore(_rag_settings(tmp_path))

    assert store.is_available() is False
    assert store.upsert_question(1, "text", user_id=1, tags=[]) is False
    assert store.semantic_search("anything", user_ids=[1]) == []
    store.delete_questions([1])  # 不应抛异常


def test_upsert_and_query_roundtrip(tmp_path, fake_chromadb):
    store = QuestionVectorStore(_rag_settings(tmp_path))
    ok = store.upsert_question(7, "判别式问题", user_id=1, tags=["方程"])
    assert ok
    collection = fake_chromadb["collections"]["questions"]
    assert collection.upserts[0]["ids"] == ["7"]
    assert collection.upserts[0]["metadatas"][0]["user_id"] == 1

    collection.query_result = {
        "ids": [["7", "8", "9"]],
        "distances": [[0.1, 0.2, 0.3]],
        "documents": [["判别式", "几何", "概率"]],
        "metadatas": [[{"tags": "方程"}, {"tags": "几何"}, {"tags": "概率"}]],
    }
    hits = store.semantic_search("判别式", user_ids=[1])
    # top_k=2 生效（配置 rag_top_k=2）；semantic_search 不排除自身
    assert [h.question_id for h in hits] == [7, 8]
    assert hits[0].tags == ["方程"]

    similar = store.similar_questions("判别式", user_ids=[1], exclude_id=7)
    # similar 尊重 exclude_id，且同样 top_k=2
    assert [h.question_id for h in similar] == [8, 9]


def test_delete_calls_collection(tmp_path, fake_chromadb):
    store = QuestionVectorStore(_rag_settings(tmp_path))
    store.delete_questions([3, 4])
    collection = fake_chromadb["collections"]["questions"]
    assert collection.deleted == [["3", "4"]]


def test_disabled_rag_reports_unavailable(tmp_path):
    settings = Settings(rag_enabled=False, chroma_dir=tmp_path / "c", _env_file=None)  # type: ignore[call-arg]
    store = QuestionVectorStore(settings)
    assert store.is_available() is False
    assert store.upsert_question(1, "t", user_id=1, tags=[]) is False
