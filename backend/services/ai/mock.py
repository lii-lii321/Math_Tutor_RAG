"""演示模式提供商：无 API Key 时返回固定的结构化解析。

保证评审者 / 面试官克隆后零配置即可跑通完整链路（上传 → 结构化解析 → 入库 → 向量索引 → 复习）。
"""
from __future__ import annotations

from backend.models.schemas import AIProviderInfo, QuestionAnalysis
from backend.services.ai.base import BaseAIProvider

_DEMO_ANALYSIS = QuestionAnalysis(
    knowledge_points=["一元二次方程", "判别式", "代数运算"],
    analysis=(
        "**【演示模式】** 以下为固定示例解析，配置 `AI_API_KEY` 后将调用真实视觉模型。\n\n"
        "### 1. 识别题目\n"
        "已知关于 $x$ 的一元二次方程 $x^2 - 2(k-1)x + k^2 = 0$ 有两个实数根，求 $k$ 的取值范围。\n\n"
        "### 2. 找错误\n"
        "常见错误是忽略判别式的符号条件，直接使用韦达定理导致范围扩大。\n\n"
        "### 3. 正确步骤\n"
        "由有两个实数根，得判别式：\n"
        "$$\\Delta = 4(k-1)^2 - 4k^2 \\ge 0$$\n"
        "化简得 $k^2 - 2k + 1 - k^2 \\ge 0$，即 $-2k + 1 \\ge 0$，解得 $k \\le \\tfrac{1}{2}$。"
    ),
    answer="$k \\le \\dfrac{1}{2}$",
    difficulty="medium",
    tags=["一元二次方程", "判别式"],
    mistake_cause="混淆「两个相等实数根」与「两个实数根」时对判别式取等号的边界处理不清。",
    followup_question=(
        "已知关于 $x$ 的方程 $x^2 - (m+2)x + m = 0$ 有两个不相等的实数根，求 $m$ 的取值范围。"
    ),
)


class MockProvider(BaseAIProvider):
    def _complete(self, image_bytes: bytes, mime_type: str, prompt: str) -> str:
        return _DEMO_ANALYSIS.model_dump_json()

    def chat(self, messages: list[dict]) -> str:
        last_user = next(
            (m["content"] for m in reversed(messages) if m["role"] == "user"),
            "",
        )
        return (
            "**【演示模式】** 已收到你的追问：" + last_user[:80] + "\n\n"
            "配置 `AI_API_KEY` 后，老师会结合题目背景给出真实讲解。"
            "这里先给一个通用提示：先确认题目考查的知识点，"
            "再从已知条件出发逐步推导，检查每一步的适用条件（例如判别式、定义域）。"
        )

    def provider_info(self) -> AIProviderInfo:
        return AIProviderInfo(
            provider="mock",
            model="demo-analysis-v1",
            configured=True,
            demo_mode=True,
        )
