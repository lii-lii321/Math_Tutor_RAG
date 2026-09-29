"""数值验证：随机取值代入等式两侧，符号化简失败时的兜底。"""
from __future__ import annotations

import random

import sympy


def numeric_equation_holds(
    lhs: sympy.Expr, rhs: sympy.Expr, var_name: str, samples: int = 5
) -> bool | None:
    """数值检验等式两侧是否恒等；无法取值或定义域内无有效样本时返回 None。"""
    symbol = sympy.Symbol(var_name)
    # 括号必须显式：|- 优先级高于 |，不加大括号会把 rhs 的变量留在 free 里恒返回 None
    free = (lhs.free_symbols | rhs.free_symbols) - {symbol}
    if free:
        return None  # 多变量暂不支持
    try:
        lhs_f = sympy.lambdify(symbol, lhs, modules=["math"])
        rhs_f = sympy.lambdify(symbol, rhs, modules=["math"])
    except Exception:  # noqa: BLE001
        return None

    # 固定种子是刻意为之：数值采样需要可复现，这里不是密码学场景
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
