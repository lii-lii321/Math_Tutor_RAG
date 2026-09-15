"""Tool-use 对话 Agent：OpenAI function calling 循环。

LLM 通过工具调用自主编排错题本操作，
用户用自然语言说需求，Agent 决定调哪个工具、调几次、如何组合结果。
"""
from __future__ import annotations

import json

from backend.config import get_settings
from backend.services.agent_tools import build_tools
from backend.services.question_service import QuestionService
from backend.utils.logging import get_logger

logger = get_logger("agent")

MAX_TOOL_ROUNDS = 8

SYSTEM_PROMPT = (
    "你是 MathMaster Edu 错题本的学习助手。"
    "用户会用自然语言提出需求（搜索错题、录入题目、安排复习、查看学情等），"
    "你可以调用工具来完成。规则："
    "1. 操作前先想清楚需要哪些信息，不确定就先查询；"
    "2. 涉及写操作（录题/评分）时向用户确认关键参数；"
    "3. 回答用简体中文，引用错题时带上 ID 和标签。"
)


class AgentSession:
    """单用户的 Agent 会话：维护消息历史并执行工具调用循环。"""

    def __init__(self, user_id: int):
        self.user_id = user_id
        self.service = QuestionService()
        self.tools = build_tools(self.service, user_id)
        self._handlers = {t.name: t.handler for t in self.tools}
        self.history: list[dict] = [
            {"role": "system", "content": SYSTEM_PROMPT}
        ]

    def _tool_schemas(self) -> list[dict]:
        return [t.openai_schema() for t in self.tools]

    def _execute_tool(self, name: str, arguments: str) -> str:
        handler = self._handlers.get(name)
        if handler is None:
            return f"未知工具: {name}"
        try:
            args = json.loads(arguments) if arguments else {}
            return handler(**args)
        except json.JSONDecodeError:
            return f"参数 JSON 解析失败: {arguments}"
        except Exception as exc:  # noqa: BLE001 - 工具异常回传给 LLM 自行纠正
            logger.warning("工具 %s 执行失败: %s", name, exc)
            return f"工具执行出错: {exc}"

    def chat(self, user_message: str) -> str:
        """处理一条用户消息，返回 Agent 的最终文字回复。"""
        self.history.append({"role": "user", "content": user_message})

        from openai import OpenAI

        settings = get_settings()
        client = OpenAI(
            api_key=settings.ai_api_key or "not-configured",
            base_url=settings.ai_base_url,
            timeout=settings.ai_timeout_seconds,
        )

        for _ in range(MAX_TOOL_ROUNDS):
            response = client.chat.completions.create(
                model=settings.ai_model,
                messages=self.history,
                tools=self._tool_schemas(),
            )
            message = response.choices[0].message

            if message.tool_calls:
                self.history.append(message.model_dump())
                for call in message.tool_calls:
                    result = self._execute_tool(call.function.name, call.function.arguments)
                    self.history.append(
                        {
                            "role": "tool",
                            "tool_call_id": call.id,
                            "content": result,
                        }
                    )
                continue  # 工具结果回传后让 LLM 继续推理

            content = message.content or ""
            self.history.append({"role": "assistant", "content": content})
            return content

        return "这个需求比较复杂，我先做了一部分。你可以拆成几个小步骤再试试。"
