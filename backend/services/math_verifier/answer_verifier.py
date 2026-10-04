"""统一验证入口：编排 SymPy/数值验证方法，产出 VerificationResult。"""
from __future__ import annotations

from backend.services.ai.telemetry import record_event
from backend.services.math_verifier.models import VerificationResult
from backend.services.math_verifier.sympy_verifier import (
    check_derivative_inverse,
    check_solution_substitution,
)
from backend.utils.logging import get_logger

logger = get_logger("math_verifier")

_VERIFIERS = (
    ("solution_substitution", check_solution_substitution),
    ("derivative_inverse", check_derivative_inverse),
)


def verify_answer(
    question_text: str, solution_text: str, answer_text: str
) -> VerificationResult:
    """验证 AI 答案的数学一致性。

    策略：依次尝试各验证方法；任一方法明确 failed 即 failed；
    任一 verified 即 verified；全部无法判定则 uncertain。
    """
    methods: list[str] = []
    details: list[str] = []
    results: list[tuple[str, float, str]] = []

    for name, verifier in _VERIFIERS:
        try:
            outcome = verifier(question_text or "", solution_text or "", answer_text or "")
        except Exception as exc:  # noqa: BLE001 - 单个验证器异常不影响整体
            # v2.11 教训：这里的静默曾是「验证器上线即失效数日无人知」的根源；
            # 降级保留，但必须留痕（遥测 + 告警日志），发生率可在 summarize() 复盘
            outcome = None
            logger.warning("验证器 %s 异常，已跳过: %s", name, exc)
            record_event(f"math_verify_error:{name}", error=f"{type(exc).__name__}: {exc}")
        if outcome is None:
            continue
        status, confidence, detail = outcome
        methods.append(name)
        details.append(f"{name}: {detail}")
        results.append((status, confidence, detail))

    if not methods:
        return VerificationResult(
            status="uncertain",
            confidence=0.0,
            methods=[],
            details="题面与答案无法配对出可验证的数学结构",
        )

    if any(status == "failed" for status, _, _ in results):
        failed = next(r for r in results if r[0] == "failed")
        return VerificationResult(
            status="failed",
            confidence=failed[1],
            methods=methods,
            details="；".join(details),
        )

    verified = next((r for r in results if r[0] == "verified"), None)
    if verified is not None:
        return VerificationResult(
            status="verified",
            confidence=verified[1],
            methods=methods,
            details="；".join(details),
        )

    # 全部 uncertain：聚合置信度与明细，不再抛 StopIteration 丢证明
    confidence = round(sum(r[1] for r in results) / len(results), 2)
    return VerificationResult(
        status="uncertain",
        confidence=confidence,
        methods=methods,
        details="；".join(details),
    )
