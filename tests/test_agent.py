"""Tool-use Agent 循环测试（mock OpenAI 客户端，验证编排逻辑）。"""
from __future__ import annotations

import json

import pytest

from backend.services.agent import AgentSession, _trim_history
from backend.services.question_service import QuestionService


class _FakeToolCall:
    def __init__(self, call_id: str, name: str, arguments: str):
        self.id = call_id
        self.function = type("Fn", (), {"name": name, "arguments": arguments})()


class _FakeMessage:
    def __init__(self, content=None, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls

    def model_dump(self):
        return {"role": "assistant", "content": self.content, "tool_calls": [
            {"id": tc.id, "type": "function",
             "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
            for tc in (self.tool_calls or [])
        ]}


class _FakeChoice:
    def __init__(self, message):
        self.message = message


class _FakeResponse:
    def __init__(self, message):
        self.choices = [_FakeChoice(message)]


class _FakeCompletions:
    """按轮次回放预设响应：轮 1 返回 tool_calls，轮 2 返回文字。"""

    def __init__(self, script: list):
        self._script = list(script)
        self.requests: list[dict] = []

    def create(self, **kwargs):
        self.requests.append(kwargs)
        script_item = self._script.pop(0)
        if "tool_calls" in script_item:
            calls = [
                _FakeToolCall(f"call_{i}", tc["name"], tc["arguments"])
                for i, tc in enumerate(script_item["tool_calls"])
            ]
            return _FakeResponse(_FakeMessage(tool_calls=calls))
        return _FakeResponse(_FakeMessage(content=script_item["content"]))


class _FakeChat:
    def __init__(self, script):
        self.completions = _FakeCompletions(script)


class _FakeOpenAI:
    def __init__(self, script):
        self.chat = _FakeChat(script)


@pytest.fixture
def service():
    from backend.database import SessionLocal

    return QuestionService(session_factory=SessionLocal)


@pytest.fixture
def agent_session(service, student_user):
    return AgentSession(user_id=student_user.id)


def test_agent_single_turn_no_tools(monkeypatch, agent_session):
    monkeypatch.setattr(
        "openai.OpenAI",
        lambda **kw: _FakeOpenAI([{"content": "你好！我是错题本助手。"}]),
    )
    reply = agent_session.chat("你好")
    assert "助手" in reply
    assert agent_session.history[-1]["role"] == "assistant"


def test_agent_tool_loop_search_then_answer(monkeypatch, agent_session, student_user):
    from backend.database import SessionLocal

    # 建立有错题的用户绑定 agent（tools 归属该用户）
    student = student_user

    saved, _ = QuestionService(session_factory=SessionLocal).analyze_and_save(
        student.id, b"\xff\xd8" + b"z" * 16, user_tags=["几何"]
    )

    # 重新绑定 agent 到该用户
    bound = AgentSession(user_id=student.id)
    monkeypatch.setattr(
        "openai.OpenAI",
        lambda **kw: _FakeOpenAI([
            {"tool_calls": [{"name": "search_questions", "arguments": json.dumps({"keyword": "几何"})}]},
            {"content": "找到了你的几何错题！"},
        ]),
    )
    reply = bound.chat("我有哪些几何错题？")
    assert "几何" in reply or "错题" in reply
    # 循环历史包含工具调用与结果
    roles = [m["role"] for m in bound.history]
    assert "tool" in roles


def test_agent_max_rounds_guard(monkeypatch, agent_session):
    # 无限工具调用 → 达到上限后优雅退出
    infinite_tool = {"tool_calls": [{"name": "get_weekly_report", "arguments": "{}"}]}
    script = [infinite_tool] * 10
    monkeypatch.setattr("openai.OpenAI", lambda **kw: _FakeOpenAI(script))
    reply = agent_session.chat("无限循环测试")
    assert "复杂" in reply or "拆" in reply  # 兜底提示


def test_extract_cited_ids_and_warning():
    from backend.services.agent import citation_warning, extract_cited_ids

    assert extract_cited_ids("见 #12 与 #7，共 2 题") == {12, 7}
    assert extract_cited_ids("# 标题不是引用") == set()
    assert citation_warning("见 #12", {12, 7}) == ""
    warning = citation_warning("见 #12 与 #99", {12})
    assert "#99" in warning and "#12" not in warning.split("：")[-1].split("，")[0]


def test_agent_annotates_unverified_citations(monkeypatch, student_user):
    from backend.database import SessionLocal

    QuestionService(session_factory=SessionLocal).analyze_and_save(
        student_user.id, b"\xff\xd8" + b"z" * 16, user_tags=["几何"]
    )
    bound = AgentSession(user_id=student_user.id)
    monkeypatch.setattr(
        "openai.OpenAI",
        lambda **kw: _FakeOpenAI([
            {"tool_calls": [{"name": "search_questions", "arguments": json.dumps({"keyword": "几何"})}]},
            {"content": "你的几何错题见 #999"},
        ]),
    )
    reply = bound.chat("我有哪些几何错题？")
    assert "引用校验" in reply and "#999" in reply


def test_agent_no_tool_turn_skips_citation_check(monkeypatch, agent_session):
    monkeypatch.setattr(
        "openai.OpenAI",
        lambda **kw: _FakeOpenAI([{"content": "上一题是 #12，可以再看看。"}]),
    )
    reply = agent_session.chat("继续讲讲")
    assert "引用校验" not in reply


# ---------- 会话历史窗口裁剪（v2.21） ----------

def _msg(role: str, content: str = "x", **extra) -> dict:
    message = {"role": role, "content": content}
    message.update(extra)
    return message


def _system() -> dict:
    return {"role": "system", "content": "sys"}


def test_trim_history_short_history_unchanged():
    """未超上界的历史原样返回（返回拷贝，不共享可变对象）。"""
    history = [_system(), _msg("user", "你好"), _msg("assistant", "好的")]
    trimmed = _trim_history(history, 60)
    assert trimmed == history
    assert trimmed is not history


def test_trim_history_caps_long_history_with_system_head():
    """100 条历史裁剪为 ≤ 60+1 条：首条保留 system、末条不丢、非 system ≤60。"""
    history = [_system()]
    for i in range(50):
        history.append(_msg("user", f"u{i}"))
        history.append(_msg("assistant", f"a{i}"))
    trimmed = _trim_history(history, 60)
    assert len(trimmed) <= 61
    assert trimmed[0] == _system()
    assert trimmed[-1] == history[-1]
    assert sum(1 for m in trimmed if m["role"] != "system") <= 60


def test_trim_history_cut_lands_on_user_boundary_no_orphan_pairs():
    """切点对齐 user 边界：assistant(tool_calls) 与其 tool 结果不被拆散成孤儿对。"""
    history = [_system()]
    for i in range(40):
        history.append(_msg("user", f"u{i}"))
        history.append(
            _msg(
                "assistant",
                None,
                tool_calls=[
                    {"id": f"c{i}", "type": "function",
                     "function": {"name": "search_questions", "arguments": "{}"}}
                ],
            )
        )
        history.append(_msg("tool", "结果", tool_call_id=f"c{i}"))

    trimmed = _trim_history(history, 60)
    assert trimmed[0] == _system()
    assert trimmed[1]["role"] == "user", "窗口首条非 system 消息必须是 user"
    for i, message in enumerate(trimmed):
        if message.get("tool_calls"):
            assert i + 1 < len(trimmed) and trimmed[i + 1]["role"] == "tool"
        if message["role"] == "tool":
            assert i > 0 and trimmed[i - 1].get("tool_calls")


def test_trim_history_is_pure_function():
    """纯函数：不修改传入的 history（脱 Streamlit 可单测）。"""
    history = [_system()] + [_msg("user", f"u{i}") for i in range(80)]
    snapshot = [dict(m) for m in history]
    _trim_history(history, 60)
    assert [dict(m) for m in history] == snapshot


def test_trim_history_without_system_head():
    """无 system 头的退化输入：仍按窗口裁剪，孤儿对不出现。"""
    history = [
        _msg(
            "assistant",
            None,
            tool_calls=[{"id": "c0", "type": "function",
                         "function": {"name": "t", "arguments": "{}"}}],
        ),
        _msg("tool", "r", tool_call_id="c0"),
        _msg("user", "u1"),
        _msg("assistant", "a1"),
    ]
    trimmed = _trim_history(history, 2)
    assert trimmed[-1] == history[-1]
    assert trimmed[0]["role"] == "user"
