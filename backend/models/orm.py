"""SQLAlchemy ORM 模型。

三张核心表：users / questions / review_logs。
questions 内嵌 SM-2 复习调度字段，review_logs 记录每次复习明细用于掌握度分析。
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from backend.config import get_settings


class Base(DeclarativeBase):
    pass


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(128))
    role: Mapped[str] = mapped_column(String(16), default="student")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    questions: Mapped[list[Question]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    def display_name(self) -> str:
        return self.username


class Question(Base):
    """一道错题：原图 + AI 结构化解析 + SM-2 复习调度状态。"""

    __tablename__ = "questions"
    __table_args__ = (
        Index("ix_questions_user_created", "user_id", "created_at"),
        Index("ix_questions_due", "user_id", "due_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)

    image_path: Mapped[str | None] = mapped_column(String(512))
    # AI 解析（Markdown）
    content_markdown: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text, default="")
    knowledge_points: Mapped[list] = mapped_column(JSON, default=list)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    difficulty: Mapped[str] = mapped_column(String(16), default="medium")
    followup_question: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(16), default="ai")  # ai / manual
    user_note: Mapped[str | None] = mapped_column(Text)
    ocr_text: Mapped[str | None] = mapped_column(Text)  # 原图 OCR 文字（可选特性）
    image_hash: Mapped[str | None] = mapped_column(String(64), index=True)  # 原图 SHA-256，去重用

    # 数学验证（Batch 03）
    verification_status: Mapped[str | None] = mapped_column(
        String(16)
    )  # verified / failed / uncertain
    verification_confidence: Mapped[float | None] = mapped_column(Float)
    verification_methods: Mapped[list | None] = mapped_column(JSON, default=list)
    verified_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))

    # SM-2 调度状态
    reps: Mapped[int] = mapped_column(Integer, default=0)
    ease: Mapped[float] = mapped_column(Float, default=lambda: get_settings().review_default_ease)
    interval_days: Mapped[float] = mapped_column(Float, default=0)
    due_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    last_reviewed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped[User] = relationship(back_populates="questions")
    review_logs: Mapped[list[ReviewLog]] = relationship(
        back_populates="question", cascade="all, delete-orphan"
    )
    comments: Mapped[list[Comment]] = relationship(
        back_populates="question", cascade="all, delete-orphan", order_by="Comment.created_at"
    )

    def is_due(self, now: dt.datetime | None = None) -> bool:
        now = now or _utcnow()
        if self.due_at is None:
            return True
        due = self.due_at if self.due_at.tzinfo else self.due_at.replace(tzinfo=dt.timezone.utc)
        return due <= now


class Comment(Base):
    """错题批注：教师对学生错题的留言（也可用于学生自注）。"""

    __tablename__ = "comments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    question_id: Mapped[int] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"), index=True
    )
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    question: Mapped[Question] = relationship(back_populates="comments")
    author: Mapped[User] = relationship()


class KnowledgePoint(Base):
    """知识点实体（规范化名称，支持后续依赖图谱扩展）。"""

    __tablename__ = "knowledge_points"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    subject: Mapped[str | None] = mapped_column(String(32))
    description: Mapped[str | None] = mapped_column(Text)
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("knowledge_points.id", ondelete="SET NULL")
    )


class QuestionKnowledgePoint(Base):
    """错题 ↔ 知识点 多对多关联。"""

    __tablename__ = "question_knowledge_points"
    __table_args__ = (
        Index("ix_qkp_question_kp", "question_id", "knowledge_point_id", unique=True),
        Index("ix_qkp_kp_question", "knowledge_point_id", "question_id"),
    )

    question_id: Mapped[int] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"), primary_key=True
    )
    knowledge_point_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_points.id", ondelete="CASCADE"), primary_key=True
    )


class Job(Base):
    """异步任务记录（图片 AI 解析等耗时操作的队列追踪）。"""

    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)  # uuid4
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String(32), default="analyze_image")
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending/running/success/failed
    payload: Mapped[dict] = mapped_column(JSON, default=dict)  # 原始文件名/mime/参数
    result: Mapped[dict | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    finished_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


class ReviewLog(Base):
    """一次复习动作的明细，SM-2 参数演进与掌握度统计的依据。"""

    __tablename__ = "review_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    question_id: Mapped[int] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)

    grade: Mapped[str] = mapped_column(String(8))  # again / hard / good / easy
    quality: Mapped[int] = mapped_column(Integer)  # SM-2 q: 0/3/4/5
    prev_interval: Mapped[float] = mapped_column(Float, default=0)
    next_interval: Mapped[float] = mapped_column(Float, default=0)
    ease_after: Mapped[Decimal] = mapped_column(Float, default=0)
    reviewed_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    question: Mapped[Question] = relationship(back_populates="review_logs")


class Conversation(Base):
    """AI Tutor 对话（Batch 07）：服务端持久化，支持跨端「继续刚才的学习」。"""

    __tablename__ = "conversations"
    __table_args__ = (Index("ix_conversations_user_updated", "user_id", "updated_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)  # uuid4
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(128), default="新对话")
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    messages: Mapped[list[ConversationMessage]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="ConversationMessage.created_at",
    )


class SchoolClass(Base):
    """班级（Batch 10 多租户）：教师拥有的学生分组，决定教师的可见范围。"""

    __tablename__ = "classes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64))
    teacher_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    members: Mapped[list[ClassMember]] = relationship(
        back_populates="school_class", cascade="all, delete-orphan"
    )


class ClassMember(Base):
    """班级成员：学生 ↔ 班级 多对多。"""

    __tablename__ = "class_members"
    __table_args__ = (Index("ix_classmember_student_class", "student_id", "class_id"),)

    class_id: Mapped[int] = mapped_column(
        ForeignKey("classes.id", ondelete="CASCADE"), primary_key=True
    )
    student_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )

    school_class: Mapped[SchoolClass] = relationship(back_populates="members")


class ConversationMessage(Base):
    """对话消息明细：user / assistant 原文，tool 行记录工具调用审计。"""

    __tablename__ = "conversation_messages"
    __table_args__ = (Index("ix_convmsg_conv_created", "conversation_id", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(16))  # user / assistant / tool
    content: Mapped[str] = mapped_column(Text, default="")
    tool_name: Mapped[str | None] = mapped_column(String(64))  # role=tool 时记录
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    conversation: Mapped[Conversation] = relationship(back_populates="messages")
