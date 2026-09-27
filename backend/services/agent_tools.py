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

    def mastery_profile() -> str:
        """知识点掌握度画像：每个知识点的掌握度、题数与薄弱状态。"""
        items = service.mastery_profile(user_id)
        return _clean(
            {
                "count": len(items),
                "knowledge_points": [
                    {
                        "name": item.knowledge_point,
                        "mastery": round(item.mastery, 3),
                        "question_count": item.question_count,
                        "due_count": item.due_count,
                        "status": item.status_label,
                    }
                    for item in items
                ],
            }
        )

    def today_review_plan(size: int = 10) -> str:
        """今日自适应复习计划：到期题优先 + 薄弱知识点加固，附推荐理由。"""
        plan = service.today_plan(user_id, size=min(int(size), 30))
        return _clean(
            {
                "count": len(plan),
                "items": [
                    {
                        "id": item.question.id,
                        "reason": item.reason,
                        "tags": item.question.tags,
                        "difficulty": item.question.difficulty,
                    }
                    for item in plan
                ],
            }
        )

    # ---------- AI Tutor 工具（Batch 07） ----------

    def get_learning_profile() -> str:
        """学习画像总览：错题量/到期/已掌握/连续打卡 + 周报 + 薄弱知识点 Top5。"""
        stats = service.dashboard_stats(user_id)
        profile = service.mastery_profile(user_id, limit=5)
        return _clean(
            {
                "total": stats["total"],
                "due": stats["due"],
                "mastered": stats["mastered"],
                "streak": stats["streak"],
                "weekly": stats["weekly"],
                "weak_knowledge_points": [
                    {
                        "name": item.knowledge_point,
                        "mastery": round(item.mastery, 3),
                        "status": item.status_label,
                    }
                    for item in profile
                    if item.status != "solid"
                ],
            }
        )

    def get_weak_knowledge_points() -> str:
        """薄弱知识点列表：掌握度 < 0.7 的全部知识点，按掌握度升序。"""
        items = [
            item
            for item in service.mastery_profile(user_id)
            if item.status != "solid"
        ]
        return _clean(
            {
                "count": len(items),
                "knowledge_points": [
                    {
                        "name": item.knowledge_point,
                        "mastery": round(item.mastery, 3),
                        "question_count": item.question_count,
                        "due_count": item.due_count,
                        "status": item.status_label,
                    }
                    for item in items
                ],
            }
        )

    def get_recent_mistakes(limit: int = 5) -> str:
        """最近录入的错题（新→旧），供分析近期问题。"""
        recent = service.list_questions(user_id, semantic=False, limit=min(int(limit), 20))
        return _clean(
            {
                "count": len(recent),
                "questions": [
                    {
                        "id": q.id,
                        "snippet": q.content_markdown[:80],
                        "knowledge_points": q.knowledge_points,
                        "tags": q.tags,
                        "difficulty": q.difficulty,
                        "date": q.created_at.strftime("%Y-%m-%d") if q.created_at else "",
                    }
                    for q in recent
                ],
            }
        )

    def get_review_history(limit: int = 10) -> str:
        """最近复习记录：评分、间隔与题目摘要（新→旧）。"""
        rows = service.recent_reviews(user_id, limit=min(int(limit), 30))
        return _clean({"count": len(rows), "reviews": rows})

    def generate_practice_set(size: int = 5, knowledge_point: str = "") -> str:
        """生成练习小卷：指定知识点取该组错题；未指定则按薄弱知识点 + 到期优先组卷。"""
        if knowledge_point.strip():
            questions = service.list_questions(
                user_id, tag=knowledge_point.strip(), semantic=False, limit=min(int(size), 20)
            )
            reason = f"知识点专项：{knowledge_point.strip()}"
        else:
            plan = service.today_plan(user_id, size=min(int(size), 20))
            questions = [item.question for item in plan]
            reason = "自适应组卷（薄弱知识点 + 到期优先）"
        return _clean(
            {
                "basis": reason,
                "count": len(questions),
                "questions": [
                    {
                        "id": q.id,
                        "snippet": q.content_markdown[:80],
                        "knowledge_points": q.knowledge_points,
                        "tags": q.tags,
                        "difficulty": q.difficulty,
                    }
                    for q in questions
                ],
            }
        )

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
        AgentTool(
            name="get_mastery_profile",
            description="获取知识点掌握度画像（每个知识点的掌握度与薄弱状态）",
            parameters={"type": "object", "properties": {}},
            handler=mastery_profile,
        ),
        AgentTool(
            name="get_today_review_plan",
            description="获取今日自适应复习计划（SM-2 到期优先 + 薄弱知识点加固）",
            parameters={
                "type": "object",
                "properties": {
                    "size": {"type": "integer", "description": "计划条数上限，默认 10"},
                },
            },
            handler=today_review_plan,
        ),
        AgentTool(
            name="get_learning_profile",
            description="获取学习画像总览（错题量/到期/已掌握/连续打卡/周报/薄弱知识点）",
            parameters={"type": "object", "properties": {}},
            handler=get_learning_profile,
        ),
        AgentTool(
            name="get_weak_knowledge_points",
            description="获取薄弱知识点列表（掌握度未达 0.7，按掌握度升序）",
            parameters={"type": "object", "properties": {}},
            handler=get_weak_knowledge_points,
        ),
        AgentTool(
            name="get_recent_mistakes",
            description="获取最近录入的错题列表",
            parameters={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "返回条数上限，默认 5"},
                },
            },
            handler=get_recent_mistakes,
        ),
        AgentTool(
            name="get_review_history",
            description="获取最近的复习记录（评分/间隔/摘要）",
            parameters={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "返回条数上限，默认 10"},
                },
            },
            handler=get_review_history,
        ),
        AgentTool(
            name="generate_practice_set",
            description="生成练习小卷（可指定知识点，否则按薄弱知识点+到期自适应组卷）",
            parameters={
                "type": "object",
                "properties": {
                    "size": {"type": "integer", "description": "题量，默认 5"},
                    "knowledge_point": {"type": "string", "description": "知识点名称（可选）"},
                },
            },
            handler=generate_practice_set,
        ),
    ]
