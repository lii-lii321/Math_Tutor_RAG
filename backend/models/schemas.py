"""Pydantic 数据契约：AI 结构化输出、API 入参、视图层传输对象。

边界处的数据一律经过 Pydantic 校验（配置 / AI 响应 / 表单入参）。
"""
from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, Field, field_validator


# ---------------- AI 结构化输出 ----------------
class QuestionAnalysis(BaseModel):
    """视觉模型对一道错题的结构化解析结果。"""

    knowledge_points: list[str] = Field(
        default_factory=list, min_length=1, max_length=6, description="考察的核心知识点"
    )
    analysis: str = Field(min_length=10, description="分步骤详细解析，Markdown 格式")
    answer: str = Field(min_length=1, description="最终正确答案")
    difficulty: Literal["easy", "medium", "hard"] = "medium"
    tags: list[str] = Field(default_factory=list, max_length=6, description="归档标签")
    mistake_cause: str = Field(default="", description="常见出错原因分析")
    followup_question: str = Field(default="", description="一道举一反三的变式练习题")

    @field_validator("knowledge_points", "tags")
    @classmethod
    def _clean_strings(cls, value: list[str]) -> list[str]:
        cleaned = [v.strip() for v in value if v and v.strip()]
        return cleaned or value

    def merged_tags(self, user_tags: list[str]) -> list[str]:
        """AI 标签与用户手填标签合并去重，保持顺序稳定。"""
        seen: list[str] = []
        for tag in [*user_tags, *self.tags, *self.knowledge_points]:
            normalized = tag.strip()
            if normalized and normalized not in seen:
                seen.append(normalized)
        return seen


class AIProviderInfo(BaseModel):
    provider: str
    model: str
    configured: bool
    demo_mode: bool


# ---------------- 视图层传输对象 ----------------
class QuestionOut(BaseModel):
    """错题在界面层的展示形态，隔离 ORM 细节。"""

    id: int
    user_id: int
    image_path: str | None
    content_markdown: str
    answer: str
    knowledge_points: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    difficulty: str = "medium"
    followup_question: str | None = None
    source: str = "ai"
    reps: int = 0
    ease: float = 2.5
    interval_days: float = 0
    due_at: dt.datetime | None = None
    last_reviewed_at: dt.datetime | None = None
    created_at: dt.datetime | None = None

    @classmethod
    def from_orm_model(cls, q) -> QuestionOut:  # noqa: ANN001 - ORM 实例
        return cls(
            id=q.id,
            user_id=q.user_id,
            image_path=q.image_path,
            content_markdown=q.content_markdown,
            answer=q.answer,
            knowledge_points=list(q.knowledge_points or []),
            tags=list(q.tags or []),
            difficulty=q.difficulty,
            followup_question=q.followup_question,
            source=q.source,
            reps=q.reps,
            ease=q.ease,
            interval_days=q.interval_days,
            due_at=q.due_at,
            last_reviewed_at=q.last_reviewed_at,
            created_at=q.created_at,
        )


class TagStat(BaseModel):
    tag: str
    count: int
    mastery: float = Field(ge=0.0, le=1.0, default=0.0)


class RegisterInput(BaseModel):
    username: str = Field(min_length=2, max_length=32)
    password: str = Field(min_length=6, max_length=64)
    role: Literal["student", "teacher"] = "student"

    @field_validator("username")
    @classmethod
    def _username_rules(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("用户名不能为空白")
        return stripped


class LoginResult(BaseModel):
    ok: bool
    user_id: int | None = None
    username: str | None = None
    role: str | None = None
    message: str = ""
