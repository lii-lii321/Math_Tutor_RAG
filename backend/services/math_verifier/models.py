"""数学验证结果模型。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass
class VerificationResult:
    """数学答案验证结果。

    status:
      - verified  通过至少一种验证方法
      - failed    至少一种方法明确证明答案错误
      - uncertain 无法自动验证（解析失败/题型不支持）
    """

    status: Literal["verified", "failed", "uncertain"]
    confidence: float = 0.0  # 0~1，对 status 的置信度
    methods: list[str] = field(default_factory=list)
    details: str = ""

    @property
    def user_hint(self) -> str:
        if self.status == "verified":
            return "✓ 数学一致性已验证"
        if self.status == "failed":
            return "⚠️ 验证未通过：答案疑似有误，请人工确认"
        return "⚠️ 当前答案无法自动验证，请人工确认"
