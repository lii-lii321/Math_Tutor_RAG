"""统一验证入口：编排 SymPy/数值验证方法，产出 VerificationResult。"""
from __future__ import annotations

from backend.services.math_verifier.models import VerificationResult
from backend.services.math_verifier.sympy_verifier import (
    check_derivative_inverse,
    check_solution_substitution,
)

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
        except Exception:  # noqa: BLE001 - 单个验证器异常不影响整体
            outcome = None
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

    verified = next(r for r in results if r[0] == "verified")
    return VerificationResult(
        status="verified",
        confidence=verified[1],
        methods=methods,
        details="；".join(details),
    )
