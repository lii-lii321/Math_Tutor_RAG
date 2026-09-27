"""AI Tutor 对话持久化服务（Batch 07）。

conversations + conversation_messages 两张表；tool 行仅作审计，
重建 LLM 历史时只回放 user / assistant 文本（见 history_for_agent）。
"""
from __future__ import annotations

import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from backend.models.orm import Conversation, ConversationMessage
from backend.utils.logging import get_logger

logger = get_logger(__name__)

MAX_TITLE_LEN = 24
MESSAGES_CAP = 400  # 单对话消息数上限，防御性截断


class ConversationService:
    """对话 CRUD 与历史重建；session-per-operation 与其余服务一致。"""

    def __init__(
        self,
        session_factory: sessionmaker | Callable[[], Iterator[Session]] | None = None,
    ):
        self._session_factory = session_factory

    @contextmanager
    def _session(self) -> Iterator[Session]:
        if self._session_factory is None:
            from backend.database import SessionLocal

            factory: sessionmaker = SessionLocal
        else:
            factory = self._session_factory  # type: ignore[assignment]
        session = factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def _get_owned(self, session: Session, conversation_id: str, user_id: int) -> Conversation | None:
        return (
            session.execute(
                select(Conversation).where(
                    Conversation.id == conversation_id,
                    Conversation.user_id == user_id,
                )
            )
            .scalar_one_or_none()
        )

    def create(self, user_id: int, title: str = "新对话") -> dict:
        conversation_id = uuid.uuid4().hex
        with self._session() as session:
            conversation = Conversation(
                id=conversation_id,
                user_id=user_id,
                title=(title or "新对话")[:128],
            )
            session.add(conversation)
            session.flush()
            return self._to_dict(conversation, message_count=0)

    def list_for_user(self, user_id: int, limit: int = 50) -> list[dict]:
        with self._session() as session:
            rows = (
                session.execute(
                    select(Conversation)
                    .where(Conversation.user_id == user_id)
                    .order_by(Conversation.updated_at.desc())
                    .limit(limit)
                )
                .scalars()
                .all()
            )
            counts: dict[str, int] = {}
            if rows:
                counts = {
                    conversation_id: count
                    for conversation_id, count in session.execute(
                        select(
                            ConversationMessage.conversation_id,
                            func.count(),
                        )
                        .where(
                            ConversationMessage.conversation_id.in_(
                                [c.id for c in rows]
                            )
                        )
                        .group_by(ConversationMessage.conversation_id)
                    ).all()
                }
            return [self._to_dict(c, counts.get(c.id, 0)) for c in rows]

    def messages(
        self, conversation_id: str, user_id: int, limit: int = 200
    ) -> list[dict] | None:
        """对话消息列表；对话不存在或非本人返回 None。"""
        with self._session() as session:
            conversation = self._get_owned(session, conversation_id, user_id)
            if conversation is None:
                return None
            rows = (
                session.execute(
                    select(ConversationMessage)
                    .where(ConversationMessage.conversation_id == conversation_id)
                    .order_by(ConversationMessage.created_at.asc())
                    .limit(limit)
                )
                .scalars()
                .all()
            )
            return [
                {
                    "role": row.role,
                    "content": row.content,
                    "tool_name": row.tool_name,
                    "created_at": row.created_at,
                }
                for row in rows
            ]

    def append_many(
        self,
        conversation_id: str,
        user_id: int,
        entries: list[tuple[str, str, str | None]],
    ) -> bool:
        """批量追加消息 entries=[(role, content, tool_name)]；标题取首条用户消息自动生成。"""
        if not entries:
            return True
        with self._session() as session:
            conversation = self._get_owned(session, conversation_id, user_id)
            if conversation is None:
                return False
            count = (
                session.execute(
                    select(func.count()).where(
                        ConversationMessage.conversation_id == conversation_id
                    )
                ).scalar_one()
            )
            for role, content, tool_name in entries[: max(0, MESSAGES_CAP - count)]:
                session.add(
                    ConversationMessage(
                        conversation_id=conversation_id,
                        role=role,
                        content=content or "",
                        tool_name=tool_name,
                    )
                )
            first_user = next((c for r, c, _ in entries if r == "user" and c), None)
            if conversation.title == "新对话" and first_user:
                conversation.title = first_user.strip()[:MAX_TITLE_LEN] or "新对话"
            return True

    def history_for_agent(
        self, conversation_id: str, user_id: int, max_messages: int = 20
    ) -> list[dict] | None:
        """重建 LLM 历史：仅 user/assistant 文本，最近 max_messages 条。"""
        with self._session() as session:
            conversation = self._get_owned(session, conversation_id, user_id)
            if conversation is None:
                return None
            rows = (
                session.execute(
                    select(ConversationMessage)
                    .where(ConversationMessage.conversation_id == conversation_id)
                    .order_by(ConversationMessage.created_at.desc())
                    .limit(max_messages)
                )
                .scalars()
                .all()
            )
        return [
            {"role": row.role, "content": row.content}
            for row in reversed(rows)
            if row.role in ("user", "assistant") and row.content
        ]

    def delete(self, conversation_id: str, user_id: int) -> bool:
        with self._session() as session:
            conversation = self._get_owned(session, conversation_id, user_id)
            if conversation is None:
                return False
            session.delete(conversation)
            return True

    @staticmethod
    def _to_dict(conversation: Conversation, message_count: int) -> dict:
        return {
            "id": conversation.id,
            "title": conversation.title,
            "created_at": conversation.created_at,
            "updated_at": conversation.updated_at,
            "message_count": message_count,
        }
