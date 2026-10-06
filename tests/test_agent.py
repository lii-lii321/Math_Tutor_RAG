"""Tool-use Agent 循环测试（mock OpenAI 客户端，验证编排逻辑）。"""
from __future__ import annotations

import json

import pytest

from backend.services.agent import AgentSession
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
