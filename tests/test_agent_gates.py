"""Agent 写操作门与错误分类测试（提升项 #13/#14）。"""
from __future__ import annotations

import json

import pytest

from backend.services import agent as agent_mod
from backend.services.agent import AgentSession, reset_write_limiters


@pytest.fixture(autouse=True)
def _clean_write_limiters():
    reset_write_limiters()
    yield
    reset_write_limiters()


@pytest.fixture
def session(student_user):
    return AgentSession(user_id=student_user.id)


def _call(session, name, **args) -> str:
    return session._execute_tool(name, json.dumps(args))


def test_write_tool_requires_confirm(session, student_user):
    """写操作缺 confirm：拒绝执行且不落库。"""
    result = _call(session, "add_text_question", content_markdown="确认门测试题")
    assert result.startswith("ERROR[param]")
    assert "confirm" in result
    hits = session.service.list_questions(
        student_user.id, keyword="确认门测试题", semantic=False
    )
    assert not hits  # 未执行


def test_write_tool_executes_with_confirm(session, student_user):
    """携带 confirm=true：正常执行落库。"""
    result = _call(
        session,
        "add_text_question",
        content_markdown="确认门执行测试题",
        confirm=True,
    )
    assert result.startswith("{") and "已存入错题本" in result
    hits = session.service.list_questions(
        student_user.id, keyword="确认门执行测试题", semantic=False
    )
    assert len(hits) == 1


def test_write_quota_denied_when_exhausted(session, student_user):
    """日配额用尽：ERROR[permission]，即使带 confirm 也不执行。"""
    agent_mod._write_limiter(student_user.id, 50)  # 按默认配额预热缓存
    assert (student_user.id, 50) in agent_mod._write_limiters
    # 预耗配额（配额键与工具调用共用 agent_write:{uid}）
    from backend.utils.request_limiter import RequestRateLimiter

    agent_mod._write_limiters[(student_user.id, 50)] = RequestRateLimiter(
        1, window_seconds=86400
    )
    agent_mod._write_limiters[(student_user.id, 50)].allow(
        f"agent_write:{student_user.id}"
    )

    result = _call(
        session, "add_text_question", content_markdown="配额测试题", confirm=True
    )
    assert result.startswith("ERROR[permission]")
    assert "配额" in result


def test_error_taxonomy_by_exception_type(session, monkeypatch):
    """ValueError→business / PermissionError→permission / 其他→internal。"""
    from backend.services.agent_tools import AgentTool

    def _raise(exc):
        def handler(**kwargs):
            raise exc

        return handler

    fake = AgentTool(
        name="fake",
        description="test",
        parameters={"type": "object", "properties": {}},
        handler=_raise(ValueError("业务规则拒绝")),
    )
    monkeypatch.setitem(session._tool_meta, "fake", fake)
    assert _call(session, "fake").startswith("ERROR[business]")

    fake_perm = AgentTool(
        name="fake_perm",
        description="test",
        parameters={"type": "object", "properties": {}},
        handler=_raise(PermissionError("无权访问")),
    )
    monkeypatch.setitem(session._tool_meta, "fake_perm", fake_perm)
    assert _call(session, "fake_perm").startswith("ERROR[permission]")

    fake_boom = AgentTool(
        name="fake_boom",
        description="test",
        parameters={"type": "object", "properties": {}},
        handler=_raise(RuntimeError("db down")),
    )
    monkeypatch.setitem(session._tool_meta, "fake_boom", fake_boom)
    assert _call(session, "fake_boom").startswith("ERROR[internal]")


def test_unknown_tool_and_bad_json_are_param_errors(session):
    assert _call(session, "no_such_tool").startswith("ERROR[param]")
    bad = session._execute_tool("search_questions", "{not json")
    assert bad.startswith("ERROR[param]")
