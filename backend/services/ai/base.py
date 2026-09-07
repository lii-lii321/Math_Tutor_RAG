"""AI 提供商抽象基类：统一的错题解析接口 + 共享提示词与解析逻辑。"""
from __future__ import annotations

import abc
import json
import re

from backend.config import Settings, get_settings
from backend.models.schemas import AIProviderInfo, QuestionAnalysis
from backend.utils.logging import get_logger

logger = get_logger("ai")

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


def build_user_prompt(hint: str) -> str:
    prompt = "请分析这张图片中的数学错题。\n"
    if hint:
        prompt += f"学生的补充说明：{hint}\n"
    return prompt + JSON_INSTRUCTION


class AIMessageError(RuntimeError):
    """模型未返回可解析的结构化结果。"""


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
        reply = self.chat(messages)
        if not reply or not reply.strip():
            raise AIMessageError("模型返回了空响应")
        return reply.strip()

    def analyze_question(
        self, image_bytes: bytes, mime_type: str = "image/jpeg", hint: str = ""
    ) -> QuestionAnalysis:
        """带重试的结构化错题解析。"""
        prompt = build_user_prompt(hint)
        last_error: Exception | None = None

        for attempt in range(1, self.settings.ai_max_retries + 1):
            try:
                raw = self._complete(image_bytes, mime_type, prompt)
                return parse_analysis(raw)
            except Exception as exc:  # noqa: BLE001 - 统一进入重试
                last_error = exc
                logger.warning("AI 调用第 %s 次失败: %s", attempt, exc)
        raise AIMessageError(f"AI 解析失败（已重试 {self.settings.ai_max_retries} 次）: {last_error}")


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
