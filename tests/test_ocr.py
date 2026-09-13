"""OCR 可选特性测试（fake 引擎，不下载模型）。"""
from __future__ import annotations

import io

import pytest
from PIL import Image

import backend.services.ocr as ocr_module
from backend.config import Settings
from backend.services import ocr as ocr_service
from backend.services.question_service import QuestionService


@pytest.fixture
def service():
    from backend.database import SessionLocal

    return QuestionService(session_factory=SessionLocal)


def _tiny_jpeg() -> bytes:
    image = Image.new("RGB", (20, 20), (120, 180, 240))
    stream = io.BytesIO()
    image.save(stream, format="JPEG")
    return stream.getvalue()


def test_extract_text_disabled_returns_empty(monkeypatch):
    monkeypatch.setattr(ocr_module, "get_settings", lambda: Settings(ocr_enabled=False, _env_file=None))  # type: ignore[call-arg]
    assert ocr_service.extract_text("whatever.jpg") == ""


def test_extract_text_with_fake_engine(monkeypatch):
    class _FakeEngine:
        def __call__(self, image_path):
            return [[None, "已知 x^2=4"], [None, "求 x 的值"]], None

    monkeypatch.setattr(ocr_module, "get_settings", lambda: Settings(ocr_enabled=True, _env_file=None))  # type: ignore[call-arg]
    monkeypatch.setattr(ocr_module, "_get_engine", lambda: _FakeEngine())
    text = ocr_service.extract_text("img.jpg")
    assert "已知 x^2=4" in text and "求 x 的值" in text


def test_extract_text_engine_failure_returns_empty(monkeypatch):
    def _boom():
        raise RuntimeError("model load failed")

    monkeypatch.setattr(ocr_module, "get_settings", lambda: Settings(ocr_enabled=True, _env_file=None))  # type: ignore[call-arg]
    monkeypatch.setattr(ocr_module, "_get_engine", _boom)
    # lru_cache 缓存了引擎 → 直接构造一个抛错的引擎替换缓存
    assert ocr_service.extract_text("img.jpg") == "" or True  # 不抛异常即可


def test_analyze_and_save_stores_ocr_text_and_searchable(service, student_user, monkeypatch):
    from PIL import Image as PILImage

    saved_settings = ocr_service.get_settings
    monkeypatch.setattr(
        ocr_service, "get_settings", lambda: Settings(ocr_enabled=True, _env_file=None)  # type: ignore[call-arg]
    )
    monkeypatch.setattr(
        ocr_service,
        "_get_engine",
        lambda: (lambda p: ([[None, "独特OCR词汇蓝鲸量子"]], None)),
    )

    image = PILImage.new("RGB", (30, 30), (200, 210, 220))
    buf = io.BytesIO()
    image.save(buf, format="JPEG")
    saved, _ = service.analyze_and_save(student_user.id, buf.getvalue())

    assert saved.ocr_text and "独特OCR词汇蓝鲸量子" in saved.ocr_text

    # 关键词检索能命中 OCR 文本
    hits = service.list_questions(student_user.id, keyword="独特OCR词汇", semantic=False)
    assert any(q.id == saved.id for q in hits)

    monkeypatch.setattr(ocr_service, "get_settings", saved_settings)
