"""算术恒等式验证：答案文本中的纯数字算术链核对。

动机（2026-10-27 真实数据实测）：七年级错题答案以「解：22+40+58+42+26+44+62＝294」
式算术链为主，现有两类方法（解代入/导数互逆）结构性不覆盖——59/59 全部 uncertain。

设计（2026-10-29 真实数据验收后定稿）：
- 只处理**单行内**的纯数字链（含小数、+ - × ÷ 四则、全角运算符归一）；
  跨行匹配会把上一步结果与下一步拼成假恒等式（实测 #83/#95）；
- 含字母/变量的段一律跳过（解代入方法的领地）；边界校验拒绝更大表达式
  的子串链（m-1+1 里的 1+1、1.2 里的 2，实测 #43/#66）；
- 等号链（a=b=c）逐段求值：全等 → verified（正向证据）；
- **所有不匹配一律 uncertain（疑似算术不一致，请人工确认），绝不 failed**：
  本方法的输入常是教师参考答案（数学上定义正确）+ 公式图片丢失后的残缺
  文本——任何 failed 都大概率是抽取伪影而非真错误（实测 6/6 failed 全为
  误判）。整数/小数的差异性质保留在详情文案里供人工参考。
"""
from __future__ import annotations

import re

import sympy

from backend.utils.logging import get_logger

logger = get_logger("math_verifier")

# 全角运算符/等号归一
_NORMALIZE = str.maketrans("＝＋－×÷ｘＸ", "=+-*/xX")
# 算术段：可选负号 + 数字（可小数）+ 可选四则续写（单行内：不含换行空白）
_SEG = r"-?\d+(?:\.\d+)?(?:[ \t]*[+\-*/][ \t]*-?\d+(?:\.\d+)?)*"
_CHAIN_RE = re.compile(rf"{_SEG}(?:[ \t]*=[ \t]*{_SEG})+")
# 变量痕迹：段内含字母即整体跳过（变量方程属解代入方法管）
_LETTER_RE = re.compile(r"[a-zA-Z]")
_DECIMAL_RE = re.compile(r"\.\d")
_OP_RE = re.compile(r"[+\-*/]")


def _boundary_ok(text: str, start: int, end: int) -> bool:
    """链边界校验（真实数据实测的三类误配防线）：

    - 链起点左邻是字母/数字/'.'/')' → 是更大表达式（变量式/小数/符号式）
      的子串，拒绝（如 m-1+1 里的 1+1、1.2 里的 2）；
    - 链终点右邻是字母/数字/'.'/'(' → 同理拒绝（如 202 截自 2025）。
    """
    if start > 0:
        prev = text[start - 1]
        if prev.isalnum() or prev in ").%":
            return False
    if end < len(text):
        nxt = text[end]
        if nxt.isalnum() or nxt in ".(":
            return False
    return True


def _segment_value(segment: str):
    """算术段 → 精确值（小数转 Rational 避免浮点误差）；不可解析返回 None。"""
    expr = segment.strip().replace(" ", "")
    if not expr or _LETTER_RE.search(expr):
        return None
    try:
        return sympy.parse_expr(
            re.sub(r"(\d+\.\d+)", r'Rational("\1")', expr),
            local_dict={"Rational": sympy.Rational},
            evaluate=True,
        )
    except Exception:  # noqa: BLE001 - 单段解析失败跳过该链
        return None


def check_arithmetic_chains(
    question_text: str, solution_text: str, answer_text: str
) -> tuple[str, float, str] | None:
    """核对答案文本（单行内）的算术恒等链；无可用链返回 None。"""
    del solution_text  # 统一三参签名
    text = (answer_text or "").translate(_NORMALIZE)
    checked = 0
    suspicions: list[str] = []

    for match in _CHAIN_RE.finditer(text):
        if not _boundary_ok(text, match.start(), match.end()):
            continue
        segments = [s.strip() for s in match.group(0).split("=")]
        if len(segments) < 2 or not any(_OP_RE.search(s) for s in segments):
            continue  # 纯数字平移（如编号/单位换行）不是恒等式
        if any(_LETTER_RE.search(s) for s in segments):
            continue  # 含变量的等式不是算术恒等式
        values = [_segment_value(s) for s in segments]
        if any(v is None for v in values):
            continue
        head = values[0]
        if not isinstance(head, sympy.Expr):
            continue
        has_decimal = any(_DECIMAL_RE.search(s) for s in segments)
        mismatches = [
            (seg, value)
            for seg, value in zip(segments[1:], values[1:], strict=False)
            if not isinstance(value, sympy.Expr) or sympy.simplify(head - value) != 0
        ]
        checked += len(segments) - 1  # 恒等关系数：n 段链含 n-1 个等式
        for seg, value in mismatches:
            if not isinstance(value, sympy.Expr):
                suspicions.append(f"{match.group(0).strip()} → {seg} 无法解析")
                continue
            rel = abs(float(head - value)) / max(abs(float(value)), 1e-12)
            if not has_decimal:
                suspicion = "整数算术不等（无舍入可能）"
            elif rel <= 0.01:
                suspicion = "数值差异 ≤1%（可能为舍入写法）"
            else:
                suspicion = f"数值差异 {rel:.1%}"
            suspicions.append(f"{match.group(0).strip()} → {seg} 应为 {head}（{suspicion}）")

    if checked == 0:
        return None
    if suspicions:
        return (
            "uncertain",
            0.6,
            f"疑似算术不一致（{len(suspicions)} 处，文本可能因公式图丢失而残缺，请人工确认）："
            + "；".join(suspicions[:3]),
        )
    return (
        "verified",
        0.9,
        f"{checked} 条算术恒等式全部成立",
    )
