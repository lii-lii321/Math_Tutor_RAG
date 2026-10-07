"""Anki 牌组导出测试：.apkg 结构、指纹 guid 稳定性、媒体、防御分支。

全程零 AI 调用；图片经测试 DATA_DIR 的 local 存储后端 materialize。
"""
from __future__ import annotations

import io
import json
import os
import sqlite3
import sys
import tempfile
import uuid
import zipfile

import pytest

from backend.database import SessionLocal
from backend.models.orm import Question
from backend.services.anki_export import generate_anki_deck
from backend.services.question_service import QuestionService


@pytest.fixture
def service():
    return QuestionService(session_factory=SessionLocal)


@pytest.fixture
def owner():
    from backend.database import session_scope
    from backend.models.orm import User

    with session_scope() as session:
        user = User(username=f"anki_{uuid.uuid4().hex[:8]}", password_hash="x", role="student")
        session.add(user)
        session.commit()
        return user.id


def _make_question(service, user_id: int, content: str, answer: str = "x=1", tags=None):
    return service.create_manual_question(
        user_id, content_markdown=content, answer=answer, tags=tags or ["anki"]
    )


def _attach_image(service, user_id: int, question_id: int) -> str:
    """给题目挂一张真实存储图（local 后端），返回库存 key。"""
    from PIL import Image

    image = Image.new("RGB", (8, 8), (10, 120, 220))
    stream = io.BytesIO()
    image.save(stream, format="JPEG")
    key = service._persist_image(user_id, stream.getvalue())
    with SessionLocal() as session:
        row = session.get(Question, question_id)
        row.image_path = key
        session.commit()
    return key


def _guids_and_fields(apkg: bytes) -> tuple[list[str], list[str]]:
    """从 .apkg（zip）取出 collection.anki2 的 guid 与首字段（flds，\\x1f 分隔）。"""
    handle = tempfile.NamedTemporaryFile(suffix=".anki2", delete=False)  # 系统安全临时 API
    conn = None
    try:
        with handle:
            handle.write(zipfile.ZipFile(io.BytesIO(apkg)).read("collection.anki2"))
        conn = sqlite3.connect(handle.name)
        rows = conn.execute("SELECT guid, flds FROM notes").fetchall()
    finally:
        if conn is not None:
            conn.close()
        os.unlink(handle.name)
    return [r[0] for r in rows], [r[1].split("\x1f")[0] for r in rows]


def test_apkg_opens_with_collection_and_media(service, owner):
    out = _make_question(service, owner, "带图 Anki 题：$x^2=4$", answer="x=±2")
    _attach_image(service, owner, out.id)
    fresh = service.get_question(out.id, owner)
    apkg = generate_anki_deck([fresh]).getvalue()

    archive = zipfile.ZipFile(io.BytesIO(apkg))
    assert "collection.anki2" in archive.namelist()
    media_manifest = json_media = json.loads(archive.read("media").decode("utf-8"))
    assert any(name.endswith(".jpg") for name in media_manifest.values()), media_manifest
    # media 文件真实打包在 zip 内
    for packed_name in media_manifest:
        assert packed_name in archive.namelist()
    assert json_media  # 非空映射


def test_guid_stable_same_content_and_differs_for_new_content(service, owner):
    out = _make_question(service, owner, "guid 稳定题：$y=2x$", answer="y")
    question = service.get_question(out.id, owner)

    guids_first, _ = _guids_and_fields(generate_anki_deck([question]).getvalue())
    guids_second, _ = _guids_and_fields(generate_anki_deck([question]).getvalue())
    assert guids_first == guids_second, "同内容重导出 guid 必须一致（更新原卡不堆积）"

    other = _make_question(service, owner, "guid 另一题：$y=3x$", answer="y2")
    fresh_other = service.get_question(other.id, owner)
    guids_mixed, _ = _guids_and_fields(generate_anki_deck([question, fresh_other]).getvalue())
    assert len(set(guids_mixed)) == 2, "不同内容 guid 必须不同"
    assert set(guids_first) <= set(guids_mixed)


def test_no_image_question_front_is_plain_text(service, owner):
    out = _make_question(service, owner, "无图纯文本题：求 $x$ 的值", answer="x=1")
    question = service.get_question(out.id, owner)
    apkg = generate_anki_deck([question]).getvalue()

    archive = zipfile.ZipFile(io.BytesIO(apkg))
    media_manifest = json.loads(archive.read("media").decode("utf-8") or "{}")
    assert media_manifest == {}, "无图题不应打包媒体"

    _guids, fronts = _guids_and_fields(apkg)
    assert len(fronts) == 1
    assert "无图纯文本题" in fronts[0]


def test_front_strips_markdown_markers(service, owner):
    out = _make_question(
        service, owner, "### 标题头 **加粗体** 求 $x$ 的值", answer="x=1"
    )
    question = service.get_question(out.id, owner)
    _guids, fronts = _guids_and_fields(generate_anki_deck([question]).getvalue())
    assert fronts and fronts[0]
    for marker in ("###", "**", "$$"):
        assert marker not in fronts[0], f"正面不应残留 Markdown 标记 {marker}"


def test_empty_questions_raises_value_error(owner):
    with pytest.raises(ValueError):
        generate_anki_deck([])


def test_genanki_missing_error_contains_install_hint(service, owner, monkeypatch):
    """旧环境防御：genanki 缺失时报错含 pip 安装提示。"""
    out = _make_question(service, owner, "缺依赖防御题", answer="x")
    question = service.get_question(out.id, owner)
    monkeypatch.setitem(sys.modules, "genanki", None)  # import genanki → ImportError
    with pytest.raises(RuntimeError, match="pip install genanki"):
        generate_anki_deck([question])
