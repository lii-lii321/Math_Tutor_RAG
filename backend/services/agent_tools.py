"""Agent 工具集：把 QuestionService 的领域能力包装为 LLM 可调用的工具。

每个工具 = 名称 + 描述 + JSON Schema 参数 + 同步执行函数。
同一份定义同时服务两处：
- Tool-use 对话 Agent（OpenAI function calling）
- MCP Server（Model Context Protocol）

所有工具都强制 user_id 归属，LLM 无法越权访问他人数据。
"""
from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from backend.services.question_mixins import sanitize_tags
from backend.services.question_service import QuestionService


@dataclass
class AgentTool:
    name: str
    description: str
    parameters: dict  # JSON Schema
    handler: Callable[..., str]

    def openai_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    def mcp_schema(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.parameters,
        }

    def __call__(self, **kwargs) -> str:
        return self.handler(**kwargs)


def _clean(result: Any) -> str:
    """统一序列化工具返回值，保证 LLM 可读。"""
    if result is None:
        return "（无结果）"
    if isinstance(result, str):
        return result
    return json.dumps(result, ensure_ascii=False, default=str)


def build_tools(service: QuestionService, user_id: int) -> list[AgentTool]:
    """为指定用户构建工具集（归属绑定，LLM 无法越权）。"""

    def search_questions(keyword: str, tag: str = "", limit: int = 10) -> str:
        """按关键词（支持语义）或标签检索当前用户的错题列表。"""
        results = service.list_questions(
            user_id,
            tag=tag or None,
            keyword=keyword or None,
            semantic=bool(keyword),
            limit=min(int(limit), 50),
        )
        items = [
            {
                "id": q.id,
                "tags": q.tags,
                "difficulty": q.difficulty,
                "answer": q.answer,
                "date": q.created_at.strftime("%Y-%m-%d") if q.created_at else "",
            }
            for q in results
        ]
        return _clean({"count": len(items), "questions": items})

    def add_text_question(content_markdown: str, answer: str = "", tags: str = "") -> str:
        """录入一道文本错题（自动打标签、入向量库、进入复习循环）。"""
        out = service.create_manual_question(
            user_id,
            content_markdown=content_markdown,
            answer=answer,
            tags=sanitize_tags(tags),
        )
        return _clean({"id": out.id, "message": "已存入错题本", "tags": out.tags})

    def grade_question(question_id: int, grade: str) -> str:
        """对一道错题评分：again(忘了)/hard(勉强)/good(记得)/easy(秒懂)，SM-2 自动排期。"""
        updated = service.grade_review(int(question_id), user_id, grade)
        if updated is None:
            return "错题不存在或无权访问"
        return _clean(
            {
                "id": updated.id,
                "reps": updated.reps,
                "next_interval_days": updated.interval_days,
                "next_due": updated.due_at.isoformat() if updated.due_at else None,
            }
        )

    def due_questions() -> str:
        """列出今日到期的错题（SM-2 调度）。"""
        due = service.due_questions(user_id)
        return _clean(
            {
                "count": len(due),
                "questions": [
                    {"id": q.id, "tags": q.tags, "difficulty": q.difficulty}
                    for q in due[:20]
                ],
            }
        )

    def weekly_report() -> str:
        """学习周报：本周录入/复习/正确率/活跃天数 + 上周对比。"""
        return _clean(service.dashboard_stats(user_id)["weekly"])

    def tag_usage() -> str:
        """标签用量统计：每个标签的错题数量，按题数降序。"""
        return _clean(service.tag_usage(user_id))

    return [
        AgentTool(
            name="search_questions",
            description="按关键词或标签检索用户的错题列表（支持语义搜索）",
            parameters={
                "type": "object",
                "properties": {
                    "keyword": {"type": "string", "description": "搜索关键词"},
                    "tag": {"type": "string", "description": "按标签精确筛选（可选）"},
                    "limit": {"type": "integer", "description": "返回条数上限，默认 10"},
                },
            },
            handler=search_questions,
        ),
        AgentTool(
            name="add_text_question",
            description="录入一道文本错题到错题本",
            parameters={
                "type": "object",
                "properties": {
                    "content_markdown": {"type": "string", "description": "题面与解析（Markdown）"},
                    "answer": {"type": "string", "description": "正确答案（可选）"},
                    "tags": {"type": "string", "description": "逗号分隔标签（可选）"},
                },
                "required": ["content_markdown"],
            },
            handler=add_text_question,
        ),
        AgentTool(
            name="grade_question",
            description="对错题评分（SM-2 间隔重复调度）",
            parameters={
                "type": "object",
                "properties": {
                    "question_id": {"type": "integer", "description": "错题 ID"},
                    "grade": {
                        "type": "string",
                        "enum": ["again", "hard", "good", "easy"],
                        "description": "记忆掌握程度",
                    },
                },
                "required": ["question_id", "grade"],
            },
            handler=grade_question,
        ),
        AgentTool(
            name="list_due_questions",
            description="列出今日到期、需要复习的错题",
            parameters={"type": "object", "properties": {}},
            handler=due_questions,
        ),
        AgentTool(
            name="get_weekly_report",
            description="获取学习周报（录入/复习/正确率/活跃天数）",
            parameters={"type": "object", "properties": {}},
            handler=weekly_report,
        ),
        AgentTool(
            name="get_tag_usage",
            description="获取标签用量统计",
            parameters={"type": "object", "properties": {}},
            handler=tag_usage,
        ),
    ]
