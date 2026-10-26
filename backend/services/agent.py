"""Tool-use 对话 Agent：OpenAI function calling 循环。

LLM 通过工具调用自主编排错题本操作，
用户用自然语言说需求，Agent 决定调哪个工具、调几次、如何组合结果。

Batch 07：可选会话持久化——传入 conversation_id 时，历史从服务端重建，
每轮对话（含工具调用审计）落库，支持跨端「继续刚才的学习」。
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from typing import TYPE_CHECKING

from backend.config import get_settings
from backend.services.agent_tools import build_tools
from backend.services.question_service import QuestionService
from backend.utils.logging import get_logger

if TYPE_CHECKING:  # pragma: no cover
    from backend.utils.request_limiter import RequestRateLimiter

logger = get_logger("agent")

MAX_TOOL_ROUNDS = 8
TOOL_TRACE_MAX = 400  # 落库时截断工具结果，防止审计消息膨胀

_CITED_ID_RE = re.compile(r"#(\d+)")
_TOOL_ID_RE = re.compile(r'"id"\s*:\s*(\d+)')

SYSTEM_PROMPT = (
    "你是 MathMaster Edu 错题本的 AI Tutor（学习助教）。"
    "用户会用自然语言提出需求（搜索错题、录入题目、安排复习、查看学情、分析薄弱点、生成练习等），"
    "你可以调用工具来完成。规则："
    "1. 操作前先想清楚需要哪些信息，不确定就先查询；"
    "2. 分析学情时先取掌握度画像与近期错题，再给结论；"
    "3. 写操作（录题/评分）先向用户复述关键参数，确认后携带 \"confirm\": true 调用；"
    "4. 回答用简体中文，引用错题时带上 ID 和标签；给建议时具体到知识点与题量。"
    "5. 学情结论和统计数字必须来自工具返回的数据，工具没有返回的信息不要推断或编造，"
    "查不到就直接说查不到；"
    "6. 引用的错题 ID（#数字）只能是本轮工具结果中出现过的 ID，"
    "不得编造 ID，也不要引用更早对话中提到但本轮未查询到的 ID。"
    "7. 工具失败按前缀分类处理：ERROR[param] 修正参数或向用户澄清后重试；"
    "ERROR[permission] 如实告知权限/配额限制；ERROR[business] 向用户转述业务原因；"
    "ERROR[internal] 属临时故障，至多重试一次，仍失败就告知用户稍后再试。"
    "任何失败都不得当成正常查询结果继续推理。"
)


def extract_cited_ids(text: str) -> set[int]:
    """抽取回复中引用的错题 ID（#123 形式）。"""
    return {int(m) for m in _CITED_ID_RE.findall(text or "")}


def extract_tool_ids(tool_results: list[str]) -> set[int]:
    """从本轮工具返回的 JSON 字符串中收集出现过的题目 ID。"""
    ids: set[int] = set()
    for result in tool_results:
        ids.update(int(m) for m in _TOOL_ID_RE.findall(result or ""))
    return ids


def citation_warning(content: str, available_ids: set[int]) -> str:
    """引用校验：回复引用了本轮工具结果中不存在的 ID 时返回警告行，否则空串。

    仅在本轮确实调用过工具时才有校验依据（available_ids 非空的前提由调用方保证）。
    """
    cited = extract_cited_ids(content)
    unverified = sorted(cited - available_ids)
    if not unverified:
        return ""
    listed = "、".join(f"#{i}" for i in unverified)
    return f"\n\n> ⚠️ 引用校验：{listed} 未出现在本轮查询结果中，该引用可能不准确，请以实际检索为准。"


@lru_cache(maxsize=4)
def _shared_client(api_key: str, base_url: str, timeout: float):
    """按配置复用 OpenAI 客户端（提升项 #20）。

    客户端持有 httpx 连接池，每轮对话新建会丢掉 keep-alive 复用；
    以 (api_key, base_url, timeout) 为键缓存，配置变更自动换新实例。
    """
    from openai import OpenAI

    return OpenAI(api_key=api_key, base_url=base_url, timeout=timeout)


def reset_client_cache() -> None:
    """测试钩子：清空客户端缓存（测试用 monkeypatch 注入假构造器，需每测重置）。"""
    _shared_client.cache_clear()


# 每用户 Agent 写操作日配额（服务端硬门，settings.agent_write_per_day）
_write_limiters: dict[tuple[int, int], RequestRateLimiter] = {}


def _write_limiter(user_id: int, quota: int):
    """取（或建）该用户的写配额滑动窗口；quota<=0 返回 None 表示不限。"""
    if quota <= 0:
        return None
    key = (user_id, quota)
    if key not in _write_limiters:
        from backend.utils.request_limiter import RequestRateLimiter

        _write_limiters[key] = RequestRateLimiter(quota, window_seconds=86400)
    return _write_limiters[key]


def reset_write_limiters() -> None:
    """测试钩子：清空写配额缓存。"""
    _write_limiters.clear()


def _trim_history(history: list[dict], max_messages: int) -> list[dict]:
    """会话历史窗口裁剪（纯函数，不依赖 Streamlit，可脱机单测）。

    保留首条 system + 最近 N 条非 system 消息；若窗口起点落在 assistant
    （含 tool_calls）或 tool 消息上，向前推进到最近的 user 消息边界——
    避免 assistant.tool_calls 与其 tool 结果被拆散成孤儿对。
    """
    if len(history) <= max_messages:
        return list(history)
    head = history[:1] if history and history[0].get("role") == "system" else []
    window = history[len(head):][-max_messages:]
    start = 0
    while start < len(window) and window[start].get("role") != "user":
        start += 1
    return [*head, *window[start:]]


def _annotate(content: str, tool_results: list[str]) -> str:
    """工具轮回复的引用校验；未调用工具的轮次不校验（历史上下文引用合法）。"""
    if not tool_results:
        return content
    return content + citation_warning(content, extract_tool_ids(tool_results))


class AgentSession:
    """单用户的 Agent 会话：维护消息历史并执行工具调用循环。"""

    def __init__(self, user_id: int, conversation_id: str | None = None):
        self.user_id = user_id
        self.service = QuestionService()
        self.tools = build_tools(self.service, user_id)
        self._handlers = {t.name: t.handler for t in self.tools}
        self._tool_meta = {t.name: t for t in self.tools}
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
        """执行工具：写操作过配额/确认门；失败按 ERROR[类别] 前缀返回给 LLM。

        前缀分类（提示词规则 7 教模型区分处理）：
        param（参数错误/未知工具/缺确认）、permission（权限/配额）、
        business（业务规则拒绝）、internal（临时故障）。
        全部出口（含早退）统一过 record_agent_tool_call 遥测。
        """
        result = self._dispatch_tool(name, arguments)
        from backend.observability import record_agent_tool_call

        record_agent_tool_call(
            name, "ok" if not result.startswith("ERROR[") else result[6:].split("]")[0]
        )
        return result

    def _dispatch_tool(self, name: str, arguments: str) -> str:
        tool = self._tool_meta.get(name)
        if tool is None:
            return f"ERROR[param]: 未知工具 {name}"
        if tool.requires_confirm:
            quota = get_settings().agent_write_per_day
            limiter = _write_limiter(self.user_id, quota)
            if limiter is not None and not limiter.allow(f"agent_write:{self.user_id}"):
                logger.warning(
                    "Agent 写配额用尽 user=%s（每日 %s 次）", self.user_id, quota
                )
                return (
                    f"ERROR[permission]: 今日 Agent 写操作配额已用尽（{quota} 次/天），"
                    "请告知用户明天再试或到界面手动操作"
                )
        try:
            args = json.loads(arguments) if arguments else {}
        except json.JSONDecodeError:
            return f"ERROR[param]: 参数 JSON 解析失败: {arguments}"
        if tool.requires_confirm and args.pop("confirm", None) is not True:
            return (
                "ERROR[param]: 写操作缺少确认——请先向用户复述关键参数"
                "（题面/答案/标签或题目与评分），经用户确认后携带 \"confirm\": true 重新调用"
            )
        try:
            return tool.handler(**args)
        except PermissionError as exc:
            return f"ERROR[permission]: {exc}"
        except ValueError as exc:
            return f"ERROR[business]: {exc}"
        except Exception as exc:  # noqa: BLE001 - 其余为临时/未知故障
            logger.warning("工具 %s 执行失败: %s", name, exc)
            return f"ERROR[internal]: 工具执行出错: {exc}"

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
        self.history = _trim_history(
            self.history, get_settings().agent_history_max_messages
        )

        settings = get_settings()
        client = self._client()
        turn_tool_results: list[str] = []

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
                        turn_tool_results.append(result)
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

                content = _annotate(message.content or "", turn_tool_results)
                self.history.append({"role": "assistant", "content": content})
                entries.append(("assistant", content, None))
                return content

            fallback = "这个需求比较复杂，我先做了一部分。你可以拆成几个小步骤再试试。"
            entries.append(("assistant", fallback, None))
            return fallback
        finally:
            self._persist(entries)

    def _client(self):
        settings = get_settings()
        return _shared_client(
            settings.ai_api_key or "not-configured",
            settings.ai_base_url,
            settings.ai_timeout_seconds,
        )

    def chat_stream(self, user_message: str):
        """流式处理一条用户消息：逐步 yield 文本增量，工具循环透明进行。

        每轮流式解析增量文本与工具调用；工具调用轮不产出文本（静默执行后继续）。
        """
        entries: list[tuple[str, str, str | None]] = [("user", user_message, None)]
        self.history.append({"role": "user", "content": user_message})
        self.history = _trim_history(
            self.history, get_settings().agent_history_max_messages
        )
        settings = get_settings()
        client = self._client()
        turn_tool_results: list[str] = []

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
                        turn_tool_results.append(result)
                        entries.append(
                            ("tool", f"{acc['name']}: {result[:TOOL_TRACE_MAX]}", acc["name"])
                        )
                        self.history.append(
                            {"role": "tool", "tool_call_id": acc["id"], "content": result}
                        )
                    continue  # 工具结果回传后继续下一轮

                content = _annotate(content, turn_tool_results)
                if content_parts and content != "".join(content_parts):
                    # 追加流式阶段未输出的引用校验警告行
                    yield content[len("".join(content_parts)):]
                self.history.append({"role": "assistant", "content": content})
                entries.append(("assistant", content, None))
                return

            fallback = "这个需求比较复杂，我先做了一部分。你可以拆成几个小步骤再试试。"
            entries.append(("assistant", fallback, None))
            yield fallback
        finally:
            self._persist(entries)
