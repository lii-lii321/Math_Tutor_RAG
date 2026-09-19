"""流式 Agent 循环测试（mock 流式 chunk）与异步任务服务测试。"""
from __future__ import annotations

import io
import json
import time

import pytest
from PIL import Image

from backend.database import SessionLocal
from backend.models.orm import User
from backend.services.agent import AgentSession
from backend.services.job_service import JobService
from backend.services.question_service import QuestionService


# ---------- 流式 fake ----------
class _Delta:
    def __init__(self, content=None, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls


class _TC:
    def __init__(self, index, id=None, name=None, arguments=None):
        self.index = index
        self.id = id
        self.function = type("Fn", (), {"name": name, "arguments": arguments})()


class _Chunk:
    def __init__(self, delta):
        self.choices = [type("C", (), {"delta": delta})()]


def _stream(script_chunks):
    return iter(script_chunks)


class _FakeStreamCompletions:
    def __init__(self, rounds):
        self._rounds = list(rounds)
        self.requests: list[dict] = []

    def create(self, **kwargs):
        self.requests.append(kwargs)
        return _stream(self._rounds.pop(0))


class _FakeStreamChat:
    def __init__(self, rounds):
        self.completions = _FakeStreamCompletions(rounds)


class _FakeStreamOpenAI:
    def __init__(self, rounds):
        self.chat = _FakeStreamChat(rounds)


@pytest.fixture
def service():
    return QuestionService(session_factory=SessionLocal)


def test_chat_stream_yields_and_executes_tools(monkeypatch, student_user):
    from backend.database import SessionLocal

    QuestionService(session_factory=SessionLocal).create_manual_question(
        student_user.id, content_markdown="流式检索目标题：相似三角形", tags=["几何"]
    )

    session = AgentSession(user_id=student_user.id)
    rounds = [
        # 轮 1：流式工具调用（分片到达）
        [
            _Chunk(_Delta(tool_calls=[_TC(0, id="c1", name="search_questions")])),
            _Chunk(_Delta(tool_calls=[_TC(0, arguments='{"keyword"')])),
            _Chunk(_Delta(tool_calls=[_TC(0, arguments=': "相似三角形"}')])),
        ],
        # 轮 2：流式文本
        [
            _Chunk(_Delta(content="找到")),
            _Chunk(_Delta(content="了几道相似三角形的错题")),
        ],
    ]
    monkeypatch.setattr(AgentSession, "_client", lambda self: _FakeStreamOpenAI(rounds))

    chunks = list(session.chat_stream("我有相似三角形的错题吗"))
    assert "".join(chunks) == "找到了几道相似三角形的错题"

    roles = [m["role"] for m in session.history]
    assert roles.count("tool") == 1  # 工具结果已回传
    tool_msg = next(m for m in session.history if m["role"] == "tool")
    assert json.loads(tool_msg["content"])["count"] >= 1  # 检索到目标题


def test_chat_stream_plain_text_only(monkeypatch, student_user):
    session = AgentSession(user_id=student_user.id)
    rounds = [[_Chunk(_Delta(content="你好")), _Chunk(_Delta(content="！"))]]
    monkeypatch.setattr(AgentSession, "_client", lambda self: _FakeStreamOpenAI(rounds))

    chunks = list(session.chat_stream("你好"))
    assert "".join(chunks) == "你好！"
    assert not any(m["role"] == "tool" for m in session.history)


# ---------- 异步任务 ----------
def _tiny_jpeg() -> bytes:
    image = Image.new("RGB", (16, 16), (90, 90, 200))
    buf = io.BytesIO()
    image.save(buf, format="JPEG")
    return buf.getvalue()


def test_async_analyze_job_completes(student_user):
    job_service = JobService()
    job_id = job_service.submit_analyze(
        student_user.id,
        _tiny_jpeg(),
        filename="async.jpg",
        mime_type="image/jpeg",
        tags=["异步"],
    )

    deadline = time.time() + 20
    job = None
    while time.time() < deadline:
        job = job_service.get(job_id, student_user.id)
        if job and job["status"] in ("success", "failed"):
            break
        time.sleep(0.3)

    assert job is not None and job["status"] == "success", job
    assert job["result"]["question_id"] > 0
    assert job["result"]["duplicated"] in (True, False)


def test_job_user_isolation(student_user):
    job_service = JobService()
    job_id = job_service.submit_analyze(
        student_user.id, _tiny_jpeg(), filename="iso.jpg", mime_type="image/jpeg"
    )
    # 等任务完成
    deadline = time.time() + 20
    while time.time() < deadline:
        job = job_service.get(job_id, student_user.id)
        if job and job["status"] in ("success", "failed"):
            break
        time.sleep(0.3)

    other = None
    with SessionLocal() as session:
        other = User(username="job_iso_other", password_hash="x", role="student")
        session.add(other)
        session.commit()
        other_id = other.id
    assert job_service.get(job_id, other_id) is None  # 他人不可见
