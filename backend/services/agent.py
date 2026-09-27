"""Tool-use 对话 Agent：OpenAI function calling 循环。

LLM 通过工具调用自主编排错题本操作，
用户用自然语言说需求，Agent 决定调哪个工具、调几次、如何组合结果。

Batch 07：可选会话持久化——传入 conversation_id 时，历史从服务端重建，
每轮对话（含工具调用审计）落库，支持跨端「继续刚才的学习」。
"""
from __future__ import annotations

import json

from backend.config import get_settings
from backend.services.agent_tools import build_tools
from backend.services.question_service import QuestionService
from backend.utils.logging import get_logger

logger = get_logger("agent")

MAX_TOOL_ROUNDS = 8
TOOL_TRACE_MAX = 400  # 落库时截断工具结果，防止审计消息膨胀

SYSTEM_PROMPT = (
    "你是 MathMaster Edu 错题本的 AI Tutor（学习助教）。"
    "用户会用自然语言提出需求（搜索错题、录入题目、安排复习、查看学情、分析薄弱点、生成练习等），"
    "你可以调用工具来完成。规则："
    "1. 操作前先想清楚需要哪些信息，不确定就先查询；"
    "2. 分析学情时先取掌握度画像与近期错题，再给结论；"
    "3. 涉及写操作（录题/评分）时向用户确认关键参数；"
    "4. 回答用简体中文，引用错题时带上 ID 和标签；给建议时具体到知识点与题量。"
)


class AgentSession:
    """单用户的 Agent 会话：维护消息历史并执行工具调用循环。"""

    def __init__(self, user_id: int, conversation_id: str | None = None):
        self.user_id = user_id
        self.service = QuestionService()
        self.tools = build_tools(self.service, user_id)
        self._handlers = {t.name: t.handler for t in self.tools}
        self.history: list[dict] = [
            {"role": "system", "content": SYSTEM_PROMPT}
        ]
        self.conversation_id = conversation_id
        if conversation_id:
            from backend.services.conversation_service import ConversationService

            past = ConversationService().history_for_agent(conversation_id, user_id)
            if past is None:
                raise ValueError("对话不存在或无权访问")
            self.history.extend(past)

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

    def _persist(self, entries: list[tuple[str, str, str | None]]) -> None:
        """对话与工具审计落库（未绑定会话或失败时静默跳过，不影响主流程）。"""
        if not self.conversation_id:
            return
        try:
            from backend.services.conversation_service import ConversationService

            ConversationService().append_many(
                self.conversation_id, self.user_id, entries
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("对话持久化失败: %s", exc)

    def chat(self, user_message: str) -> str:
        """处理一条用户消息，返回 Agent 的最终文字回复（非流式）。"""
        entries: list[tuple[str, str, str | None]] = [("user", user_message, None)]
        self.history.append({"role": "user", "content": user_message})

        settings = get_settings()
        client = self._client()

        try:
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
                        result = self._execute_tool(
                            call.function.name, call.function.arguments
                        )
                        entries.append(
                            ("tool", f"{call.function.name}: {result[:TOOL_TRACE_MAX]}", call.function.name)
                        )
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
                entries.append(("assistant", content, None))
                return content

            fallback = "这个需求比较复杂，我先做了一部分。你可以拆成几个小步骤再试试。"
            entries.append(("assistant", fallback, None))
            return fallback
        finally:
            self._persist(entries)

    def _client(self):
        from openai import OpenAI

        settings = get_settings()
        return OpenAI(
            api_key=settings.ai_api_key or "not-configured",
            base_url=settings.ai_base_url,
            timeout=settings.ai_timeout_seconds,
        )

    def chat_stream(self, user_message: str):
        """流式处理一条用户消息：逐步 yield 文本增量，工具循环透明进行。

        每轮流式解析增量文本与工具调用；工具调用轮不产出文本（静默执行后继续）。
        """
        entries: list[tuple[str, str, str | None]] = [("user", user_message, None)]
        self.history.append({"role": "user", "content": user_message})
        settings = get_settings()
        client = self._client()

        try:
            for _ in range(MAX_TOOL_ROUNDS):
                stream = client.chat.completions.create(
                    model=settings.ai_model,
                    messages=self.history,
                    tools=self._tool_schemas(),
                    stream=True,
                )
                content_parts: list[str] = []
                tool_calls_acc: dict[int, dict] = {}

                for chunk in stream:
                    if not chunk.choices:
                        continue
                    delta = chunk.choices[0].delta
                    if delta is None:
                        continue
                    if delta.content:
                        content_parts.append(delta.content)
                        yield delta.content
                    if delta.tool_calls:
                        for tc in delta.tool_calls:
                            acc = tool_calls_acc.setdefault(
                                tc.index, {"id": "", "name": "", "arguments": ""}
                            )
                            if tc.id:
                                acc["id"] = tc.id
                            if tc.function and tc.function.name:
                                acc["name"] += tc.function.name
                            if tc.function and tc.function.arguments:
                                acc["arguments"] += tc.function.arguments

                content = "".join(content_parts)
                if tool_calls_acc:
                    ordered = [tool_calls_acc[i] for i in sorted(tool_calls_acc)]
                    self.history.append(
                        {
                            "role": "assistant",
                            "content": content or None,
                            "tool_calls": [
                                {
                                    "id": acc["id"],
                                    "type": "function",
                                    "function": {"name": acc["name"], "arguments": acc["arguments"]},
                                }
                                for acc in ordered
                            ],
                        }
                    )
                    for acc in ordered:
                        result = self._execute_tool(acc["name"], acc["arguments"])
                        entries.append(
                            ("tool", f"{acc['name']}: {result[:TOOL_TRACE_MAX]}", acc["name"])
                        )
                        self.history.append(
                            {"role": "tool", "tool_call_id": acc["id"], "content": result}
                        )
                    continue  # 工具结果回传后继续下一轮

                self.history.append({"role": "assistant", "content": content})
                entries.append(("assistant", content, None))
                return

            fallback = "这个需求比较复杂，我先做了一部分。你可以拆成几个小步骤再试试。"
            entries.append(("assistant", fallback, None))
            yield fallback
        finally:
            self._persist(entries)
