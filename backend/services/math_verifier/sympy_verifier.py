"""SymPy 符号验证：解代入 + 导数/积分互逆检查。"""
from __future__ import annotations

import re

import sympy

from backend.services.math_verifier.latex_utils import (
    extract_equations,
    extract_math_blocks,
    extract_solution_assignments,
    latex_to_expr,
)


def check_solution_substitution(
    question_text: str, solution_text: str, answer_text: str
) -> tuple[str, float, str] | None:
    """解代入验证：题面方程 × 答案解 → 代入检验。

    返回 (status, confidence, details)；题面/答案无法配对时返回 None。
    """
    solutions = extract_solution_assignments(answer_text)
    equations = extract_equations(question_text)
    if not solutions or not equations:
        return None

    checked = 0
    for lhs, rhs, var_names in equations:
        for var, values in solutions:
            if var not in var_names:
                continue
            symbol = sympy.Symbol(var)
            for value in values:
                try:
                    diff = sympy.simplify(lhs.subs(symbol, value) - rhs.subs(symbol, value))
                except Exception:  # noqa: BLE001
                    continue
                checked += 1
                if diff != 0:
                    return (
                        "failed",
                        0.9,
                        f"解 {var}={value} 代入方程不成立（残差 {diff}）",
                    )
    if checked:
        return ("verified", 0.95, f"{checked} 个解全部通过代入检验")
    return None


def check_derivative_inverse(
    question_text: str, answer_text: str
) -> tuple[str, float, str] | None:
    """导数验证：题面给出 f(x)=g，答案给出 f'(x)=h → 检查 diff(g, x) == h。"""
    if not any(word in question_text for word in ("导数", "求导", "微分")):
        return None

    # 从题面找函数定义：f(x) = expr / y = expr
    func_expr = None
    var_name = "x"
    for block in extract_math_blocks(question_text):
        if "=" not in block:
            continue
        lhs, _, rhs = block.partition("=")
        m = re.search(r"([a-zA-Z])\s*\(\s*([a-zA-Z])\s*\)", lhs)
        if m:
            var_name = m.group(2)
            func_expr = latex_to_expr(rhs, {var_name: sympy.Symbol(var_name)})
            break
        if lhs.strip().isalpha() and len(lhs.strip()) <= 2:
            var_name = lhs.strip()
            func_expr = latex_to_expr(rhs, {var_name: sympy.Symbol(var_name)})
            break
    if func_expr is None:
        return None

    # 从答案找导数结果：f'(x) = expr / y' = expr / 导数为 expr
    derived = None
    for block in extract_math_blocks(answer_text):
        if "'" in block and "=" in block:
            _, _, rhs = block.partition("=")
            derived = latex_to_expr(rhs, {var_name: sympy.Symbol(var_name)})
            break
    if derived is None:
        return None

    symbol = sympy.Symbol(var_name)
    try:
        expected = sympy.diff(func_expr, symbol)
        diff = sympy.simplify(expected - derived)
    except Exception:  # noqa: BLE001
        return None
    if diff == 0:
        return ("verified", 0.95, f"导数互逆检验通过：d/d{var_name} {func_expr} = {derived}")
    return ("failed", 0.9, f"导数不符：期望 {expected}，答案给出 {derived}")
