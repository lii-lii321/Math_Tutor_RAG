"""AI Tutor 对话路由（Batch 07）：会话 CRUD 与持久化流式对话。"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from api.deps import get_current_user
from backend.models.orm import User
from backend.services.agent import AgentSession
from backend.services.conversation_service import ConversationService

router = APIRouter(prefix="/conversations", tags=["conversations"])


class ConversationCreate(BaseModel):
    title: str = Field(default="新对话", max_length=128)


class ConversationChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


def _service() -> ConversationService:
    return ConversationService()


@router.post("", status_code=201)
def create_conversation(
    payload: ConversationCreate, user: User = Depends(get_current_user)
) -> dict:
    return _service().create(user.id, title=payload.title)


@router.get("")
def list_conversations(
    limit: int = 50, user: User = Depends(get_current_user)
) -> list[dict]:
    return _service().list_for_user(user.id, limit=min(limit, 100))


@router.get("/{conversation_id}/messages")
def conversation_messages(
    conversation_id: str, user: User = Depends(get_current_user)
) -> list[dict]:
    rows = _service().messages(conversation_id, user.id)
    if rows is None:
        raise HTTPException(404, "对话不存在")
    return rows


@router.delete("/{conversation_id}", status_code=204)
def delete_conversation(
    conversation_id: str, user: User = Depends(get_current_user)
) -> None:
    if not _service().delete(conversation_id, user.id):
        raise HTTPException(404, "对话不存在")


@router.post("/{conversation_id}/chat/stream")
def conversation_chat_stream(
    conversation_id: str,
    payload: ConversationChatRequest,
    user: User = Depends(get_current_user),
):
    """SSE 流式对话（服务端持久化）：历史从 conversation_messages 重建。"""

    def event_gen():
        try:
            session = AgentSession(user_id=user.id, conversation_id=conversation_id)
        except ValueError as exc:
            yield f"data: {json.dumps({'error': str(exc)}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
            return
        try:
            for chunk in session.chat_stream(payload.message):
                yield f"data: {json.dumps({'delta': chunk}, ensure_ascii=False)}\n\n"
        except Exception as exc:  # noqa: BLE001 - 流中异常以事件形式告知客户端
            yield f"data: {json.dumps({'error': str(exc)}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
