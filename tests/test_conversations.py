"""AI Tutor 对话持久化 + Tutor 工具测试（Batch 07）。"""
from __future__ import annotations

import uuid

import pytest

from backend.database import SessionLocal, init_db
from backend.models.orm import User
from backend.services.agent import AgentSession
from backend.services.agent_tools import build_tools
from backend.services.conversation_service import ConversationService
from backend.services.question_service import QuestionService


@pytest.fixture
def conv_user() -> User:
    init_db(seed_users=True)
    with SessionLocal() as session:
        user = User(username=f"conv_{uuid.uuid4().hex[:10]}", password_hash="x", role="student")
        session.add(user)
        session.commit()
        session.refresh(user)
        return user


@pytest.fixture
def other_user() -> User:
    with SessionLocal() as session:
        user = User(username=f"convx_{uuid.uuid4().hex[:10]}", password_hash="x", role="student")
        session.add(user)
        session.commit()
        session.refresh(user)
        return user


@pytest.fixture
def conv_service() -> ConversationService:
    return ConversationService()


class TestConversationService:
    def test_create_and_list(self, conv_service, conv_user):
        created = conv_service.create(conv_user.id, title="导数专题")
        assert created["id"]
        assert created["title"] == "导数专题"
        listed = conv_service.list_for_user(conv_user.id)
        assert any(c["id"] == created["id"] for c in listed)

    def test_append_auto_title_and_messages(self, conv_service, conv_user):
        created = conv_service.create(conv_user.id)
        ok = conv_service.append_many(
            created["id"],
            conv_user.id,
            [
                ("user", "我最近哪里最薄弱？", None),
                ("tool", "get_weak_knowledge_points: {...}", "get_weak_knowledge_points"),
                ("assistant", "你的薄弱点是二次函数。", None),
            ],
        )
        assert ok is True
        rows = conv_service.messages(created["id"], conv_user.id)
        assert [r["role"] for r in rows] == ["user", "tool", "assistant"]
        assert rows[1]["tool_name"] == "get_weak_knowledge_points"

        updated = {c["id"]: c for c in conv_service.list_for_user(conv_user.id)}
        assert updated[created["id"]]["title"].startswith("我最近哪里")

    def test_history_for_agent_excludes_tool(self, conv_service, conv_user):
        created = conv_service.create(conv_user.id)
        conv_service.append_many(
            created["id"],
            conv_user.id,
            [
                ("user", "第一问", None),
                ("tool", "tool-trace", "some_tool"),
                ("assistant", "第一答", None),
            ],
        )
        history = conv_service.history_for_agent(created["id"], conv_user.id)
        assert history == [
            {"role": "user", "content": "第一问"},
            {"role": "assistant", "content": "第一答"},
        ]

    def test_ownership_isolation(self, conv_service, conv_user, other_user):
        created = conv_service.create(conv_user.id)
        assert conv_service.messages(created["id"], other_user.id) is None
        assert conv_service.history_for_agent(created["id"], other_user.id) is None
        assert conv_service.delete(created["id"], other_user.id) is False
        assert conv_service.delete(created["id"], conv_user.id) is True
        assert conv_service.messages(created["id"], conv_user.id) is None


class TestAgentPersistence:
    def _fake_openai(self, monkeypatch, script):
        from tests.test_agent import _FakeOpenAI

        monkeypatch.setattr("openai.OpenAI", lambda **kw: _FakeOpenAI(script))

    def test_chat_persists_messages(self, monkeypatch, conv_service, conv_user):
        conversation = conv_service.create(conv_user.id)
        session = AgentSession(user_id=conv_user.id, conversation_id=conversation["id"])
        self._fake_openai(monkeypatch, [{"content": "回答完成"}])

        reply = session.chat("帮我看看薄弱点")
        assert reply == "回答完成"

        rows = conv_service.messages(conversation["id"], conv_user.id)
        assert [(r["role"]) for r in rows] == ["user", "assistant"]
        assert rows[0]["content"] == "帮我看看薄弱点"
        assert rows[1]["content"] == "回答完成"

    def test_tool_trace_persisted(self, monkeypatch, conv_service, conv_user):
        import json as _json

        conversation = conv_service.create(conv_user.id)
        session = AgentSession(user_id=conv_user.id, conversation_id=conversation["id"])
        self._fake_openai(
            monkeypatch,
            [
                {"tool_calls": [{"name": "get_learning_profile", "arguments": _json.dumps({})}]},
                {"content": "画像分析好了"},
            ],
        )
        session.chat("分析一下我的学习情况")

        rows = conv_service.messages(conversation["id"], conv_user.id)
        tool_rows = [r for r in rows if r["role"] == "tool"]
        assert len(tool_rows) == 1
        assert tool_rows[0]["tool_name"] == "get_learning_profile"
        assert "get_learning_profile" in tool_rows[0]["content"]

    def test_resume_from_conversation(self, monkeypatch, conv_service, conv_user):
        conversation = conv_service.create(conv_user.id)
        conv_service.append_many(
            conversation["id"],
            conv_user.id,
            [
                ("user", "上一轮问题", None),
                ("assistant", "上一轮回答", None),
            ],
        )
        session = AgentSession(user_id=conv_user.id, conversation_id=conversation["id"])
        roles = [m["role"] for m in session.history]
        assert "user" in roles and "assistant" in roles

    def test_invalid_conversation_rejected(self, conv_user):
        with pytest.raises(ValueError):
            AgentSession(user_id=conv_user.id, conversation_id="no-such-id")


class TestTutorTools:
    def test_tool_count_and_registry(self, conv_user):
        service = QuestionService(session_factory=SessionLocal)
        tools = build_tools(service, conv_user.id)
        names = {t.name for t in tools}
        assert {
            "get_learning_profile",
            "get_weak_knowledge_points",
            "get_recent_mistakes",
            "get_review_history",
            "generate_practice_set",
        } <= names

    def test_tutor_tools_shapes(self, conv_user):
        import json as _json

        service = QuestionService(session_factory=SessionLocal)
        handlers = {t.name: t.handler for t in build_tools(service, conv_user.id)}

        profile = _json.loads(handlers["get_learning_profile"]())
        assert {"total", "due", "mastered", "streak", "weekly", "weak_knowledge_points"} <= set(profile)

        weak = _json.loads(handlers["get_weak_knowledge_points"]())
        assert weak == {"count": 0, "knowledge_points": []}

        practice = _json.loads(handlers["generate_practice_set"](size=3))
        assert practice["count"] == 0 and practice["questions"] == []

    def test_generate_practice_set_with_kp(self, conv_user):
        import json as _json

        service = QuestionService(session_factory=SessionLocal)
        service.create_manual_question(
            conv_user.id,
            content_markdown="向量练习题",
            knowledge_points=["平面向量"],
            tags=["平面向量"],
        )
        handlers = {t.name: t.handler for t in build_tools(service, conv_user.id)}
        practice = _json.loads(
            handlers["generate_practice_set"](size=5, knowledge_point="平面向量")
        )
        assert practice["count"] == 1
        assert practice["questions"][0]["id"]


class TestConversationsAPI:
    @pytest.fixture
    def conv_headers(self, client):
        username = f"conv_api_{uuid.uuid4().hex[:10]}"
        client.post(
            "/api/auth/register",
            json={"username": username, "password": "secret1", "role": "student"},
        )
        login = client.post(
            "/api/auth/login", json={"username": username, "password": "secret1"}
        )
        return {"Authorization": f"Bearer {login.json()['access_token']}"}

    def test_conversation_crud_api(self, client, conv_headers):
        created = client.post(
            "/api/conversations", headers=conv_headers, json={"title": "API 会话"}
        )
        assert created.status_code == 201, created.text
        conversation_id = created.json()["id"]

        listed = client.get("/api/conversations", headers=conv_headers)
        assert listed.status_code == 200
        assert any(c["id"] == conversation_id for c in listed.json())

        messages = client.get(
            f"/api/conversations/{conversation_id}/messages", headers=conv_headers
        )
        assert messages.status_code == 200
        assert messages.json() == []

        deleted = client.delete(f"/api/conversations/{conversation_id}", headers=conv_headers)
        assert deleted.status_code == 204
        assert (
            client.get(f"/api/conversations/{conversation_id}/messages", headers=conv_headers).status_code
            == 404
        )

    def test_conversation_requires_auth(self, client):
        assert client.get("/api/conversations").status_code == 401
        assert (
            client.post("/api/conversations", json={"title": "x"}).status_code == 401
        )

    def test_chat_stream_unknown_conversation(self, client, conv_headers):
        response = client.post(
            "/api/conversations/no-such-id/chat/stream",
            headers=conv_headers,
            json={"message": "你好"},
        )
        assert response.status_code == 200  # SSE 以事件返回错误
        assert "error" in response.text
