"""数值验证：随机取值代入等式两侧，符号化简失败时的兜底。"""
from __future__ import annotations

import random

import sympy


def numeric_equation_holds(
    lhs: sympy.Expr, rhs: sympy.Expr, var_name: str, value, samples: int = 5
) -> bool | None:
    """对单变量等式做数值代入检验；无法取值时返回 None。"""
    symbol = sympy.Symbol(var_name)
    free = lhs.free_symbols | rhs.free_symbols - {symbol}
    if free:
        return None  # 多变量暂不支持
    try:
        lhs_f = sympy.lambdify(symbol, lhs, modules=["math"])
        rhs_f = sympy.lambdify(symbol, rhs, modules=["math"])
    except Exception:  # noqa: BLE001
        return None

    rng = random.Random(42)
    checked = 0
    for _ in range(samples):
        x = rng.uniform(-5, 5)
        try:
            if abs(lhs_f(x) - rhs_f(x)) > 1e-6:
                return False
            checked += 1
        except Exception:  # noqa: BLE001 - 定义域外跳过
            continue
    return True if checked else None
