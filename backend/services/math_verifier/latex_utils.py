"""LaTeX/文本 → SymPy 的轻量转换与数学结构抽取。

不做完整 LaTeX 解析（antlr 依赖过重），覆盖错题本场景的高频模式：
四则、分数、根号、幂、±、不等号、常见函数。
"""
from __future__ import annotations

import re

from sympy.parsing.sympy_parser import (
    implicit_multiplication_application,
    parse_expr,
    standard_transformations,
)

_TRANSFORM = standard_transformations + (implicit_multiplication_application,)

_REPLACEMENTS = [
    (r"\\d?frac\{([^{}]*)\}\{([^{}]*)\}", r"((\1)/(\2))"),
    (r"\\sqrt\{([^{}]*)\}", r"sqrt(\1)"),
    (r"\\left", ""),
    (r"\\right", ""),
    (r"\\cdot", "*"),
    (r"\\times", "*"),
    (r"\\div", "/"),
    (r"\\leq|\\le", "<="),
    (r"\\geq|\\ge", ">="),
    (r"\\neq|\\ne", "!="),
    (r"\\infty", "oo"),
    (r"\\pi", "pi"),
    (r"\\ln", "log"),
    (r"\\log", "log"),
    (r"\\sin", "sin"),
    (r"\\cos", "cos"),
    (r"\\tan", "tan"),
    (r"\^\{(-?\d+)\}", r"**(\1)"),
    (r"\^(-?\d+)", r"**\1"),
    (r"\$\$", ""),
    (r"\$", ""),
    (r"\\,", " "),
]


def latex_to_expr(latex: str, symbols: dict | None = None):
    """把一段简化 LaTeX 转为 SymPy 表达式；解析失败返回 None。"""
    text = latex.strip()
    for pattern, repl in _REPLACEMENTS:
        text = re.sub(pattern, repl, text)
    text = text.replace("{", "(").replace("}", ")")
    text = re.sub(r"\\[a-zA-Z]+", "", text)  # 清掉剩余命令
    text = text.replace("^", "**")
    try:
        return parse_expr(
            text,
            local_dict=symbols or {},
            transformations=_TRANSFORM,
            evaluate=True,
        )
    except Exception:  # noqa: BLE001 - 解析器对任意文本会抛多种异常
        return None


def extract_math_blocks(*texts: str) -> list[str]:
    """从文本中抽取 $...$ / $$...$$ 数学块。"""
    blocks: list[str] = []
    for text in texts:
        if not text:
            continue
        blocks += re.findall(r"\$\$(.+?)\$\$", text, flags=re.DOTALL)
        blocks += re.findall(r"(?<!\$)\$(?!\$)(.+?)(?<!\$)\$(?!\$)", text)
    return [b.strip() for b in blocks if b.strip()]


def extract_solution_assignments(answer_text: str) -> list[tuple[str, list]]:
    """从答案中抽取「变量 = 值」型解，± 展开为两个值。

    支持：x = 3、x = ±3、x = \\frac{1}{2}、k \\le 1/2 视为边界不等式（跳过）。
    返回 [(变量名, [SymPy 值, ...]), ...]
    """
    results: list[tuple[str, list]] = []
    for block in extract_math_blocks(answer_text) or ([answer_text] if "=" in answer_text else []):
        for m in re.finditer(
            r"([a-zA-Z])\s*(?:=|＝)\s*(?:\\pm|±)?\s*([^，。;；\n]+)", block
        ):
            var = m.group(1)
            value_latex = m.group(2).strip()
            pm = "±" in m.group(0) or "\\pm" in m.group(0)
            if any(op in value_latex for op in ("<", ">", "<=", ">=")):
                continue  # 不等式解集不做代入验证
            base = latex_to_expr(value_latex)
            if base is None:
                continue
            if pm:
                results.append((var, [base, -base]))
            else:
                results.append((var, [base]))
    return results


def extract_equations(question_text: str) -> list[tuple]:
    """从题面抽取等式（如 x^2 = 9），返回 [(lhs_expr, rhs_expr, 变量名), ...]。"""
    equations = []
    for block in extract_math_blocks(question_text):
        if "=" not in block:
            continue
        lhs_latex, _, rhs_latex = block.partition("=")
        lhs = latex_to_expr(lhs_latex)
        rhs = latex_to_expr(rhs_latex)
        if lhs is None or rhs is None:
            continue
        free = (lhs.free_symbols | rhs.free_symbols)
        var_name = sorted(str(s) for s in free)
        equations.append((lhs, rhs, var_name))
    return equations
