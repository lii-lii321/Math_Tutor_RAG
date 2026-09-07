from __future__ import annotations

import io

from PIL import Image

from backend.services.ai.base import FOLLOWUP_SYSTEM_PROMPT, BaseAIProvider
from backend.services.ai.mock import MockProvider


def _tiny_jpeg() -> bytes:
    image = Image.new("RGB", (8, 8), color=(180, 200, 240))
    stream = io.BytesIO()
    image.save(stream, format="JPEG")
    return stream.getvalue()


def test_mock_chat_echoes_question():
    provider = MockProvider()
    reply = provider.chat(
        [
            {"role": "system", "content": FOLLOWUP_SYSTEM_PROMPT},
            {"role": "user", "content": "为什么判别式要大于等于零？"},
        ]
    )
    assert "判别式" in reply


def test_answer_followup_builds_context_and_history():
    provider = MockProvider()
    captured: list[list[dict]] = []

    def fake_chat(messages):
        captured.append(messages)
        return "回复内容"

    provider.chat = fake_chat  # type: ignore[method-assign]
    reply = provider.answer_followup(
        "考点：判别式\n解析：……",
        history=[
            {"role": "user", "content": "第一问"},
            {"role": "assistant", "content": "第一问回答"},
        ],
        user_question="第二问怎么入手？",
    )
    assert reply == "回复内容"
    sent = captured[0]
    assert sent[0]["role"] == "system"
    assert "判别式" in sent[0]["content"]
    assert sent[-1] == {"role": "user", "content": "第二问怎么入手？"}
    assert len(sent) == 4  # system + 2 历史 + 当前问题


def test_answer_followup_truncates_long_history():
    provider = MockProvider()
    captured: list[list[dict]] = []

    def fake_chat(messages):
        captured.append(messages)
        return "ok"

    provider.chat = fake_chat  # type: ignore[method-assign]
    history = [
        {"role": "user" if i % 2 == 0 else "assistant", "content": str(i)} for i in range(30)
    ]
    provider.answer_followup("ctx", history, "问")
    assert len(captured[0]) == 14  # system + 最近 12 条 + 当前问题


def test_answer_followup_rejects_empty_reply():
    provider = MockProvider()
    provider.chat = lambda messages: "  "  # type: ignore[method-assign, assignment]
    try:
        provider.answer_followup("ctx", [], "问")
        raised = False
    except Exception:  # noqa: BLE001
        raised = True
    assert raised


def test_base_provider_is_abstract():
    import pytest

    with pytest.raises(TypeError):
        BaseAIProvider()  # type: ignore[abstract]


def test_service_answer_followup_ownership(question_service, student_user, db_session):
    from backend.models.orm import User

    saved, _ = question_service.analyze_and_save(student_user.id, _tiny_jpeg())

    stranger = User(username="stranger_chat", password_hash="x", role="student")
    db_session.add(stranger)
    db_session.commit()

    reply = question_service.answer_followup(saved.id, student_user.id, [], "什么是判别式？")
    assert "判别式" in reply or "演示" in reply

    try:
        question_service.answer_followup(saved.id, stranger.id, [], "偷看别人的题")
        raised = False
    except ValueError:
        raised = True
    assert raised, "跨用户访问应被拒绝"
