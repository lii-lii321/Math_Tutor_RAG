"""错误信封测试：SSE 与全局异常处理器不得向客户端泄露内部细节（安全收口）。"""
from __future__ import annotations

import io
import uuid
from unittest.mock import MagicMock

import pytest
from PIL import Image

import api.main as api_main
import api.routers.agent as agent_router
import api.routers.conversations as conversations_router
import api.routers.questions as questions_router
from backend.services.agent import AgentSession
from backend.services.question_service import QuestionService

# 模拟内部实现细节：真实故障时绝不能出现在客户端响应里
_INTERNAL_DETAIL = "upstream https://llm-internal.example.com/v1 key=sk-secret-123"
_GENERIC_SSE_ERROR = "AI 服务暂时不可用，请稍后再试"
_GENERIC_500 = "服务器内部错误"
_GENERIC_502 = "AI 解析失败，请稍后重试或改用文本录题"


def _raise_internal(*_args, **_kwargs):
    raise RuntimeError(f"连接上游失败: {_INTERNAL_DETAIL}")


def _boom_init(self, *_args, **_kwargs):
    raise RuntimeError(f"会话构造失败 db down: {_INTERNAL_DETAIL}")


@pytest.fixture
def auth_headers(client):
    username = f"envelope_{uuid.uuid4().hex[:10]}"
    client.post(
        "/api/auth/register",
        json={"username": username, "password": "secret1", "role": "student"},
    )
    login = client.post(
        "/api/auth/login", json={"username": username, "password": "secret1"}
    )
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


@pytest.fixture
def quiet_client():
    """ServerErrorMiddleware 发送响应后会 re-raise，测试端需关闭异常上抛。"""
    from fastapi.testclient import TestClient

    from api.main import create_app

    return TestClient(create_app(), raise_server_exceptions=False)


def _assert_no_leak(response_text: str) -> None:
    for leak in (_INTERNAL_DETAIL, "RuntimeError", "Traceback", "llm-internal.example.com"):
        assert leak not in response_text


# ---------- SSE 错误事件 ----------

def test_agent_stream_error_is_generic(client, auth_headers, monkeypatch):
    monkeypatch.setattr(agent_router, "logger", MagicMock())
    monkeypatch.setattr(AgentSession, "chat_stream", lambda self, message: _raise_internal())

    response = client.post(
        "/api/agent/chat/stream", headers=auth_headers, json={"message": "你好"}
    )

    assert response.status_code == 200  # SSE 以事件形式返回错误
    assert _GENERIC_SSE_ERROR in response.text
    assert response.text.endswith("data: [DONE]\n\n")
    _assert_no_leak(response.text)
    # 原始细节只进日志
    assert _INTERNAL_DETAIL in str(agent_router.logger.warning.call_args)


def test_conversation_stream_error_is_generic(client, auth_headers, monkeypatch):
    monkeypatch.setattr(conversations_router, "logger", MagicMock())
    monkeypatch.setattr(AgentSession, "chat_stream", lambda self, message: _raise_internal())

    created = client.post(
        "/api/conversations", headers=auth_headers, json={"title": "信封测试"}
    )
    assert created.status_code == 201, created.text
    conversation_id = created.json()["id"]

    response = client.post(
        f"/api/conversations/{conversation_id}/chat/stream",
        headers=auth_headers,
        json={"message": "你好"},
    )

    assert response.status_code == 200
    assert _GENERIC_SSE_ERROR in response.text
    assert response.text.endswith("data: [DONE]\n\n")
    _assert_no_leak(response.text)
    assert _INTERNAL_DETAIL in str(conversations_router.logger.warning.call_args)


# ---------- SSE：会话构造失败（含 DB 故障等非 ValueError） ----------

def test_agent_session_init_failure_is_generic(client, auth_headers, monkeypatch):
    monkeypatch.setattr(agent_router, "logger", MagicMock())
    monkeypatch.setattr(AgentSession, "__init__", _boom_init)

    response = client.post(
        "/api/agent/chat/stream", headers=auth_headers, json={"message": "你好"}
    )

    assert response.status_code == 200  # SSE 响应头已发出，只能以事件兜底
    assert _GENERIC_SSE_ERROR in response.text
    assert response.text.endswith("data: [DONE]\n\n")
    _assert_no_leak(response.text)
    assert _INTERNAL_DETAIL in str(agent_router.logger.warning.call_args)


def test_conversation_session_init_failure_is_generic(client, auth_headers, monkeypatch):
    monkeypatch.setattr(conversations_router, "logger", MagicMock())
    monkeypatch.setattr(AgentSession, "__init__", _boom_init)

    created = client.post(
        "/api/conversations", headers=auth_headers, json={"title": "构造失败测试"}
    )
    assert created.status_code == 201, created.text

    response = client.post(
        f"/api/conversations/{created.json()['id']}/chat/stream",
        headers=auth_headers,
        json={"message": "你好"},
    )

    assert response.status_code == 200
    assert _GENERIC_SSE_ERROR in response.text
    assert response.text.endswith("data: [DONE]\n\n")
    _assert_no_leak(response.text)
    assert _INTERNAL_DETAIL in str(conversations_router.logger.warning.call_args)


# ---------- 全局 500 信封 ----------

def test_unhandled_exception_returns_uniform_envelope(quiet_client, auth_headers, monkeypatch):
    logger_mock = MagicMock()
    monkeypatch.setattr(api_main, "logger", logger_mock)
    monkeypatch.setattr(QuestionService, "list_questions", _raise_internal)

    response = quiet_client.get("/api/questions", headers=auth_headers)

    assert response.status_code == 500
    assert response.json() == {"detail": _GENERIC_500}
    _assert_no_leak(response.text)
    # 原始细节只进 logger.exception
    assert _INTERNAL_DETAIL in str(logger_mock.exception.call_args)


def test_http_exception_not_intercepted(client, auth_headers):
    response = client.get("/api/questions/99999999", headers=auth_headers)

    assert response.status_code == 404
    assert response.json()["detail"] == "错题不存在"


# ---------- AI 录题 502 信封 ----------

def _tiny_jpeg() -> bytes:
    image = Image.new("RGB", (16, 16), (120, 120, 120))
    buf = io.BytesIO()
    image.save(buf, format="JPEG")
    return buf.getvalue()


def test_analyze_failure_keeps_502_with_fixed_message(client, auth_headers, monkeypatch):
    monkeypatch.setattr(questions_router, "logger", MagicMock())
    monkeypatch.setattr(QuestionService, "analyze_and_save", _raise_internal)

    response = client.post(
        "/api/questions/analyze",
        headers=auth_headers,
        files={"image": ("t.jpg", _tiny_jpeg(), "image/jpeg")},
        data={"tags": "", "hint": ""},
    )

    assert response.status_code == 502  # 状态码与语义不变
    assert response.json()["detail"] == _GENERIC_502
    _assert_no_leak(response.text)
    assert _INTERNAL_DETAIL in str(questions_router.logger.warning.call_args)
