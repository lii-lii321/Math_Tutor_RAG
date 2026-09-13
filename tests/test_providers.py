"""OpenAI 兼容 / Gemini 提供商的请求构造与响应解析测试（mock 客户端，不出网）。"""
from __future__ import annotations

import pytest

from backend.config import Settings
from backend.services.ai.base import AIMessageError
from backend.services.ai.gemini import GeminiProvider
from backend.services.ai.openai_compat import OpenAICompatProvider


def _settings(provider: str) -> Settings:
    return Settings(
        ai_provider=provider,
        ai_api_key="test-key",
        ai_base_url="https://fake.example/v1",
        ai_model="fake-model",
        ai_max_retries=1,
        _env_file=None,  # type: ignore[call-arg]
    )


class _FakeMessage:
    def __init__(self, content: str | None):
        self.content = content


class _FakeChoice:
    def __init__(self, content: str | None):
        self.message = _FakeMessage(content)


class _FakeResponse:
    def __init__(self, content: str | None):
        self.choices = [_FakeChoice(content)]


class _FakeCompletions:
    def __init__(self, content: str | None):
        self._content = content
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return _FakeResponse(self._content)


class _FakeChat:
    def __init__(self, content: str | None):
        self.completions = _FakeCompletions(content)


class _FakeOpenAIClient:
    def __init__(self, content: str | None = "ok"):
        self.chat = _FakeChat(content)


def test_openai_compat_builds_multimodal_request(monkeypatch):
    captured: dict = {}

    class _Factory:
        def __new__(cls, **kwargs):
            captured["init"] = kwargs
            return _FakeOpenAIClient("你好")

    monkeypatch.setattr(
        "backend.services.ai.openai_compat.OpenAI", _Factory
    )
    provider = OpenAICompatProvider(_settings("openai_compatible"))
    raw = provider._complete(b"img-bytes", "image/png", "请解析")

    assert raw == "你好"
    assert captured["init"]["api_key"] == "test-key"
    assert captured["init"]["base_url"] == "https://fake.example/v1"

    call = provider._client.chat.completions.calls[0]
    assert call["model"] == "fake-model"
    system, user = call["messages"]
    assert system["role"] == "system"
    image_part, text_part = user["content"]
    assert image_part["image_url"]["url"].startswith("data:image/png;base64,")
    assert "请解析" in text_part["text"]


def test_openai_compat_empty_response_raises(monkeypatch):
    monkeypatch.setattr(
        "backend.services.ai.openai_compat.OpenAI",
        lambda **kwargs: _FakeOpenAIClient(None),
    )
    provider = OpenAICompatProvider(_settings("openai_compatible"))
    with pytest.raises(ValueError, match="空响应"):
        provider._complete(b"img", "image/jpeg", "p")


def test_openai_compat_provider_info(monkeypatch):
    monkeypatch.setattr(
        "backend.services.ai.openai_compat.OpenAI",
        lambda **kwargs: _FakeOpenAIClient(),
    )
    provider = OpenAICompatProvider(_settings("openai_compatible"))
    info = provider.provider_info()
    assert info.provider == "openai_compatible"
    assert info.configured and not info.demo_mode
    assert info.model == "fake-model"


class _FakeGenaiTypes:
    class Part:
        @staticmethod
        def from_bytes(data: bytes, mime_type: str):
            return {"data": data, "mime": mime_type}

    class Content:
        def __init__(self, role: str, parts: list):
            self.role = role
            self.parts = parts

    class GenerateContentConfig:
        def __init__(self, **kwargs):
            self.kwargs = kwargs


class _FakeGenaiModels:
    def __init__(self, text: str | None):
        self._text = text
        self.calls: list[dict] = []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)

        class _Resp:
            text = self._text

        return _Resp()


class _FakeGenaiClient:
    def __init__(self, text: str | None = "gemini-ok"):
        self.models = _FakeGenaiModels(text)


def test_gemini_chat_builds_contents(monkeypatch):
    fake_client = _FakeGenaiClient()
    monkeypatch.setattr("google.genai.Client", lambda api_key: fake_client)
    provider = GeminiProvider(_settings("gemini"))
    reply = provider.chat(
        [
            {"role": "system", "content": "system prompt"},
            {"role": "user", "content": "问题一"},
            {"role": "assistant", "content": "回答一"},
            {"role": "user", "content": "问题二"},
        ]
    )

    assert reply == "gemini-ok"
    call = fake_client.models.calls[0]
    assert call["model"] == "fake-model"
    contents = call["contents"]
    # system 不进入 contents；仅 user/assistant 交替
    assert [c.role for c in contents] == ["user", "model", "user"]
    assert contents[-1].parts[0].text == "问题二"


def test_gemini_complete_passes_image_and_json_mode(monkeypatch):
    fake_client = _FakeGenaiClient()
    monkeypatch.setattr("google.genai.Client", lambda api_key: fake_client)
    provider = GeminiProvider(_settings("gemini"))
    raw = provider._complete(b"img", "image/jpeg", "解析")
    assert raw == "gemini-ok"

    call = fake_client.models.calls[0]
    config = call["config"]
    assert config.response_mime_type == "application/json"
    assert config.system_instruction


def test_gemini_empty_response_raises(monkeypatch):
    monkeypatch.setattr(
        "google.genai.Client", lambda api_key: _FakeGenaiClient(None)
    )
    provider = GeminiProvider(_settings("gemini"))
    with pytest.raises(ValueError, match="空响应"):
        provider._complete(b"img", "image/jpeg", "p")


def test_gemini_provider_info(monkeypatch):
    monkeypatch.setattr("google.genai.Client", lambda api_key: _FakeGenaiClient())
    provider = GeminiProvider(_settings("gemini"))
    info = provider.provider_info()
    assert info.provider == "gemini"
    assert info.model == "fake-model"


def test_analyze_text_parses_and_guards_empty():
    from backend.models.schemas import AIProviderInfo
    from backend.services.ai.base import BaseAIProvider

    class _StubProvider(BaseAIProvider):
        def __init__(self):
            super().__init__(settings=_settings("mock"))
            self._chat_reply = ""

        def _complete(self, image_bytes, mime_type, prompt):  # pragma: no cover
            return ""

        def chat(self, messages):
            return self._chat_reply

        def provider_info(self):  # pragma: no cover
            return AIProviderInfo(provider="stub", model="stub", configured=True, demo_mode=True)

    provider = _StubProvider()
    provider._chat_reply = (
        '{"knowledge_points": ["方程"], "analysis": "这是一段足够长的解析。",'
        ' "answer": "x=±2", "tags": ["方程"]}'
    )
    analysis = provider.analyze_text("解方程 x^2=4")
    assert analysis.answer == "x=±2"

    provider._chat_reply = "  "
    with pytest.raises(AIMessageError):
        provider.analyze_text("任意题目")
