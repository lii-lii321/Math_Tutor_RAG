"""AI Agent 路由：SSE 流式对话。"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from api.deps import get_current_user
from backend.models.orm import User
from backend.services.agent import AgentSession

router = APIRouter(prefix="/agent", tags=["agent"])


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    history: list[dict] = Field(default_factory=list, max_length=40)


@router.post("/chat/stream")
def chat_stream(payload: ChatRequest, user: User = Depends(get_current_user)):
    """SSE 流式对话：text/event-stream，data 为 {"delta": "..."} 片段，[DONE] 结束。"""

    def event_gen():
        session = AgentSession(user_id=user.id)
        # 恢复客户端传来的对话历史（仅 user/assistant 文本消息）
        for message in payload.history:
            if message.get("role") in ("user", "assistant") and message.get("content"):
                session.history.append(
                    {"role": message["role"], "content": str(message["content"])}
                )
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
