"""AI 重试退避测试：延迟序列、次数语义、遥测不变（time.sleep 打桩零等待）。"""
from __future__ import annotations

import pytest

from backend.config import Settings
from backend.models.schemas import AIProviderInfo
from backend.services.ai import base as ai_base
from backend.services.ai.base import AIMessageError, BaseAIProvider

_VALID_PAYLOAD = (
    '{"knowledge_points":["探针"],'
    '"analysis":"分步解析内容（足够长以通过 Schema 最小长度校验）","answer":"x=1",'
    '"difficulty":"easy","tags":["t"],"mistake_cause":"m","followup_question":"f?"}'
)


class _FlakyProvider(BaseAIProvider):
    """前 failures 次抛瞬态异常，之后返回合法结构化 JSON；chat 可脚本化。"""

    def __init__(self, *, failures: int = 0, settings: Settings | None = None):
        super().__init__(settings=settings)
        self._failures = failures
        self.calls = 0
        self.chat_calls = 0
        self.chat_script: list[str] = []

    def _complete(self, image_bytes: bytes, mime_type: str, prompt: str) -> str:
        self.calls += 1
        if self.calls <= self._failures:
            raise RuntimeError("transient network error")
        return _VALID_PAYLOAD

    def chat(self, messages: list[dict]) -> str:
        self.chat_calls += 1
        if self.chat_calls <= self.chat_script_len:
            return self.chat_script[self.chat_calls - 1]
        return _VALID_PAYLOAD

    @property
    def chat_script_len(self) -> int:
        return len(self.chat_script)

    def provider_info(self) -> AIProviderInfo:
        return AIProviderInfo(provider="flaky", model="flaky", configured=True, demo_mode=True)


@pytest.fixture
def sleeps(monkeypatch):
    captured: list[float] = []

    def _fake_sleep(seconds: float) -> None:
        captured.append(seconds)

    monkeypatch.setattr(ai_base.time, "sleep", _fake_sleep)
    return captured


def test_backoff_recovers_after_two_failures(sleeps):
    """失败 2 次第 3 次成功：sleep 次数=失败次数，基数翻倍且 ≤ cap+jitter。

    抖动幅度（0.25s）小于最小基数（0.5s），故序列严格递增。
    """
    provider = _FlakyProvider(failures=2)
    analysis = provider.analyze_question(b"image-bytes")
    assert analysis.answer == "x=1"
    assert provider.calls == 3
    assert len(sleeps) == 2
    base, cap, jitter = (
        ai_base._BACKOFF_BASE_SECONDS,
        ai_base._BACKOFF_CAP_SECONDS,
        ai_base._BACKOFF_JITTER_SECONDS,
    )
    assert base <= sleeps[0] <= base + jitter  # 0.5s × 2^0 + 抖动
    assert base * 2 <= sleeps[1] <= base * 2 + jitter  # 0.5s × 2^1 + 抖动
    assert sleeps[1] > sleeps[0]  # 严格递增
    for delay in sleeps:
        assert delay <= cap + jitter  # 封顶上界


def test_backoff_exhaustion_raises_with_attempt_count(sleeps):
    """耗尽次数：最终 AIMessageError 含尝试次数，最后一次失败后不再 sleep。"""
    provider = _FlakyProvider(failures=99)
    with pytest.raises(AIMessageError) as exc_info:
        provider.analyze_question(b"image-bytes")
    assert "已重试 3 次" in str(exc_info.value)
    assert provider.calls == 3
    assert len(sleeps) == 2  # 最后一次失败后直接抛错，零 sleep


def test_max_retries_one_means_zero_sleep():
    """max_retries=1：单次失败即抛错，全程零 sleep。"""
    provider = _FlakyProvider(failures=5, settings=Settings(ai_max_retries=1))
    with pytest.raises(AIMessageError) as exc_info:
        provider.analyze_question(b"image-bytes")
    assert "已重试 1 次" in str(exc_info.value)
    assert provider.calls == 1


def test_telemetry_records_every_attempt_including_failures(sleeps, monkeypatch):
    """遥测语义不变：每次尝试（含失败）都有 track_ai_call 记录，成功置 ok。"""
    events: list[dict] = []

    class _Ctx(dict):
        def __enter__(self):
            return self

        def __exit__(self, *exc_info):
            return False

    def _fake_track(op):
        entry = _Ctx(op=op, ok=False)
        events.append(entry)
        return entry

    monkeypatch.setattr(ai_base, "track_ai_call", _fake_track)
    provider = _FlakyProvider(failures=2)
    provider.analyze_question(b"image-bytes")
    assert [e["op"] for e in events] == ["analyze_image"] * 3
    assert [e["ok"] for e in events] == [False, False, True]


class _ScriptedChatProvider(_FlakyProvider):
    """chat 按脚本返回：前 chat_failures 次给非 JSON，之后给合法拆题结果。"""

    def __init__(self, *, chat_failures: int):
        super().__init__(failures=0)
        self._chat_failures = chat_failures

    def chat(self, messages: list[dict]) -> str:
        self.chat_calls += 1
        if self.chat_calls <= self._chat_failures:
            return "不是 JSON 的输出"
        return '{"questions": [{"content": "题一", "answer": "a", "difficulty": "easy"}]}'


def test_split_questions_backoff_and_recovery(sleeps):
    """拆题路径同型收口：固定 3 次尝试、失败退避、成功返回拆题结果。"""
    provider = _ScriptedChatProvider(chat_failures=1)
    chunks = provider.split_questions("文档文本")
    assert len(chunks) == 1
    assert chunks[0]["content"] == "题一"
    assert len(sleeps) == 1
