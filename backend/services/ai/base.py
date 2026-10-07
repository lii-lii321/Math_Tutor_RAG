"""AI 提供商抽象基类：统一的错题解析接口 + 共享提示词与解析逻辑。"""
from __future__ import annotations

import abc
import json
import random
import re
import time
from collections.abc import Callable
from typing import TypeVar

from backend.config import Settings, get_settings
from backend.models.schemas import AIProviderInfo, QuestionAnalysis
from backend.services.ai.telemetry import track_ai_call
from backend.utils.logging import get_logger

logger = get_logger("ai")

# 重试退避参数：0.5s 起逐次翻倍，封顶 4s，叠加均匀抖动避免惊群
_BACKOFF_BASE_SECONDS = 0.5
_BACKOFF_CAP_SECONDS = 4.0
_BACKOFF_JITTER_SECONDS = 0.25

T = TypeVar("T")

SYSTEM_PROMPT = (
    "你是一位经验丰富、讲解亲切的数学老师。学生会上传一张写有数学错题的图片，"
    "请严谨地识别题目（包括手写内容与 LaTeX 公式），分析错误原因并给出逐步讲解。"
    "所有讲解使用简体中文，公式使用 LaTeX（$...$ 行内，$$...$$ 独立）。"
    "必须严格输出 JSON，不要输出任何 JSON 以外的内容。"
)

FOLLOWUP_SYSTEM_PROMPT = (
    "你是一位耐心的数学老师，正在就学生的一道错题进行一对一追问讲解。"
    "讲解使用简体中文，公式使用 LaTeX（$...$ 行内，$$...$$ 独立）。"
    "回答紧扣题目本身，先直接回应学生的问题，再按需展开推导；学生理解卡住时给提示而不是直接报答案。"
)

JSON_INSTRUCTION = """请只输出一个 JSON 对象，结构如下：
{
  "knowledge_points": ["3-5 个考察的核心知识点"],
  "analysis": "分步骤的详细解析，Markdown 格式，先指出错误再逐步推导",
  "answer": "最终正确答案",
  "difficulty": "easy | medium | hard",
  "tags": ["2-4 个归档标签，如：几何, 相似三角形"],
  "mistake_cause": "这类题常见的出错原因",
  "followup_question": "一道考查相同知识点的变式练习题（只给题目，不给答案）"
}"""

SPLIT_SYSTEM_PROMPT = (
    "你是数学教研助理，负责把整理好的文档切分成独立的错题卡片。"
    "必须严格输出 JSON，不要输出任何 JSON 以外的内容。"
)

SPLIT_JSON_INSTRUCTION = """任务：把下面的文档文本切分成独立的错题，每题输出一个对象：
{
  "content": "题面与解析（Markdown，保留 LaTeX 公式，尽量保留原文）",
  "answer": "最终答案（文档未给就填空字符串）",
  "knowledge_points": ["1-3 个知识点"],
  "difficulty": "easy | medium | hard"
}
只输出一个 JSON 对象：{"questions": [...]}。整份文档只有一道题时也输出同样结构。"""


def build_split_prompt(text: str) -> str:
    return f"{SPLIT_JSON_INSTRUCTION}\n\n【文档内容】\n{text[:6000]}"


def build_user_prompt(hint: str) -> str:
    prompt = "请分析这张图片中的数学错题。\n"
    if hint:
        prompt += f"学生的补充说明：{hint}\n"
    return prompt + JSON_INSTRUCTION


class AIMessageError(RuntimeError):
    """模型未返回可解析的结构化结果。"""


def _retry_with_backoff(op: str, fn: Callable[[], T], *, max_attempts: int) -> T:
    """重试收口助手：逐次执行 fn，失败按指数退避 + 抖动 sleep 后重试。

    延迟 = min(0.5 × 2^(attempt-1), 4s) + uniform(0, 0.25s)。失败次数、
    遥测（fn 内 track_ai_call）与成功路径语义由调用方保持；耗尽次数后
    抛出含尝试次数的 AIMessageError。
    """
    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 - 超时/解析失败统一重试
            last_error = exc
            logger.warning("%s 第 %s 次失败: %s", op, attempt, exc)
            if attempt < max_attempts:
                delay = min(
                    _BACKOFF_BASE_SECONDS * 2 ** (attempt - 1), _BACKOFF_CAP_SECONDS
                ) + random.uniform(0, _BACKOFF_JITTER_SECONDS)
                time.sleep(delay)
    raise AIMessageError(f"{op}失败（已重试 {max_attempts} 次）: {last_error}")


class BaseAIProvider(abc.ABC):
    """所有提供商实现同一接口，界面层与提供商解耦。"""

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()

    @abc.abstractmethod
    def _complete(self, image_bytes: bytes, mime_type: str, prompt: str) -> str:
        """调用多模态模型，返回原始文本响应。"""

    @abc.abstractmethod
    def chat(self, messages: list[dict]) -> str:
        """纯文本多轮对话：messages 为 [{"role": ..., "content": ...}, ...]。"""

    @abc.abstractmethod
    def provider_info(self) -> AIProviderInfo:
        """提供商元信息，用于界面展示运行状态。"""

    def answer_followup(
        self,
        question_context: str,
        history: list[dict],
        user_question: str,
    ) -> str:
        """围绕一道已解析错题的多轮追问讲题。"""
        messages: list[dict] = [
            {
                "role": "system",
                "content": f"{FOLLOWUP_SYSTEM_PROMPT}\n\n【题目背景】\n{question_context[:4000]}",
            },
            *history[-12:],  # 限制上下文长度，防止 token 超限
            {"role": "user", "content": user_question},
        ]
        with track_ai_call("followup_chat"):
            reply = self.chat(messages)
        if not reply or not reply.strip():
            raise AIMessageError("模型返回了空响应")
        return reply.strip()

    def analyze_text(self, text: str, hint: str = "") -> QuestionAnalysis:
        """纯文本错题解析（手动录入场景），复用结构化输出约束。"""
        prompt = (
            f"题目内容：\n{text[:4000]}\n\n"
            f"学生补充：{hint or '无'}\n\n"
            f"{JSON_INSTRUCTION}"
        )
        with track_ai_call("analyze_text"):
            raw = self.chat(
                [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": prompt}]
            )
        return parse_analysis(raw)

    def split_questions(self, text: str) -> list[dict]:
        """把结构化文档文本切分为独立错题（Word 导入场景，带重试）。

        长文本生成 JSON 耗时较长，超时/解析失败最多重试 2 次（指数退避+抖动）。
        """

        def _attempt() -> list[dict]:
            with track_ai_call("split_questions") as ctx:
                raw = self.chat(
                    [
                        {"role": "system", "content": SPLIT_SYSTEM_PROMPT},
                        {"role": "user", "content": build_split_prompt(text)},
                    ]
                )
                candidate = extract_json_block(raw)
                ctx["ok"] = candidate is not None
            if candidate is None or not isinstance(candidate.get("questions"), list):
                raise AIMessageError("模型未返回可解析的拆题结果")
            questions = [
                q
                for q in candidate["questions"]
                if isinstance(q, dict) and q.get("content")
            ]
            if not questions:
                raise AIMessageError("拆题结果为空")
            return questions

        return _retry_with_backoff("拆题", _attempt, max_attempts=3)

    def analyze_question(
        self, image_bytes: bytes, mime_type: str = "image/jpeg", hint: str = ""
    ) -> QuestionAnalysis:
        """带重试（指数退避+抖动）的结构化错题解析。"""
        prompt = build_user_prompt(hint)

        def _attempt() -> QuestionAnalysis:
            with track_ai_call("analyze_image") as ctx:
                raw = self._complete(image_bytes, mime_type, prompt)
                analysis = parse_analysis(raw)
                ctx["ok"] = True
                return analysis

        return _retry_with_backoff(
            "AI 解析", _attempt, max_attempts=self.settings.ai_max_retries
        )


def parse_analysis(raw: str) -> QuestionAnalysis:
    """从模型响应中稳健地提取 JSON 并校验为 QuestionAnalysis。

    兼容三类输出：纯 JSON、```json 围栏、前后夹杂说明文字。
    """
    candidate = extract_json_block(raw)
    if candidate is None:
        raise AIMessageError("响应中未找到 JSON 结构")
    return QuestionAnalysis.model_validate(candidate)


def extract_json_block(raw: str) -> dict | None:
    if not raw:
        return None
    text = raw.strip()
    # 1) 直接解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # 2) 提取 ```json 围栏
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced:
        try:
            return json.loads(fenced.group(1))
        except json.JSONDecodeError:
            pass
    # 3) 贪婪匹配第一个平衡的花括号块
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    return None
