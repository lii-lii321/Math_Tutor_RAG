"""数学验证引擎全覆盖测试（Batch：SymPy/数值/latex_utils/编排层）。"""
from __future__ import annotations

import sympy

from backend.services.math_verifier import answer_verifier
from backend.services.math_verifier.answer_verifier import verify_answer
from backend.services.math_verifier.latex_utils import (
    extract_equations,
    extract_math_blocks,
    extract_solution_assignments,
    latex_to_expr,
)
from backend.services.math_verifier.numeric_verifier import numeric_equation_holds
from backend.services.math_verifier.sympy_verifier import (
    check_derivative_inverse,
    check_solution_substitution,
)


class TestLatexUtils:
    def test_latex_to_expr_basic(self):
        assert latex_to_expr("x^2").equals(sympy.Symbol("x") ** 2)
        assert latex_to_expr("\\frac{1}{2}").equals(sympy.Rational(1, 2))
        assert latex_to_expr("\\sqrt{9}").equals(sympy.Integer(3))
        assert latex_to_expr("2\\cdot 3").equals(sympy.Integer(6))
        assert latex_to_expr("\\pi").equals(sympy.pi)

    def test_latex_to_expr_invalid_returns_none(self):
        assert latex_to_expr("x ^") is None
        assert latex_to_expr("f((") is None

    def test_extract_math_blocks(self):
        blocks = extract_math_blocks("已知 $x^2 = 9$，且 $$y = x + 1$$")
        assert "x^2 = 9" in blocks
        assert "y = x + 1" in blocks

    def test_extract_solution_assignments_pm_expansion(self):
        solutions = extract_solution_assignments("答案：$x = \\pm 3$")
        assert solutions == [("x", [sympy.Integer(3), sympy.Integer(-3)])]

    def test_extract_solution_assignments_skips_inequality(self):
        assert extract_solution_assignments("解集：$k \\le 1/2$") == []

    def test_extract_equations(self):
        equations = extract_equations("解方程 $x^2 = 9$")
        assert len(equations) == 1
        lhs, rhs, names = equations[0]
        assert lhs.equals(sympy.Symbol("x") ** 2)
        assert rhs.equals(sympy.Integer(9))
        assert names == ["x"]


class TestSolutionSubstitution:
    def test_verified_with_pm_pair(self):
        outcome = check_solution_substitution(
            "解方程 $x^2 = 9$", "", "解得 $x = \\pm 3$"
        )
        assert outcome is not None
        status, confidence, detail = outcome
        assert status == "verified"
        assert 2 == detail.count("x=3") + detail.count("x=-3") or "2 个解" in detail

    def test_failed_on_wrong_solution(self):
        outcome = check_solution_substitution("解方程 $x^2 = 9$", "", "解得 $x = 5$")
        assert outcome is not None and outcome[0] == "failed"

    def test_none_when_no_math(self):
        assert check_solution_substitution("纯文字题", "", "纯文字答案") is None

    def test_numeric_fallback_when_simplify_raises(self, monkeypatch):
        """化简抛异常时降级数值代入，仍能判 verified（新接线分支）。"""
        def _boom(_expr):
            raise RuntimeError("simplify down")

        monkeypatch.setattr(sympy, "simplify", _boom)
        outcome = check_solution_substitution("解方程 $x^2 = 9$", "", "解得 $x = 3$")
        assert outcome is not None and outcome[0] == "verified"
        assert "数值" in outcome[2] or "代入" in outcome[2]


class TestDerivativeInverse:
    def test_verified(self):
        outcome = check_derivative_inverse(
            "求 $f(x) = x^2$ 的导数", "", "导数为 $f'(x) = 2x$"
        )
        assert outcome is not None and outcome[0] == "verified"

    def test_failed_on_wrong_derivative(self):
        outcome = check_derivative_inverse(
            "求 $f(x) = x^2$ 的导数", "", "导数为 $f'(x) = 3x$"
        )
        assert outcome is not None and outcome[0] == "failed"

    def test_uncertain_when_symbols_disagree_but_numeric_holds(self, monkeypatch):
        """化简判不等但数值恒等 → uncertain（不再误判 failed，新接线分支）。"""
        def _fake_simplify(_expr):
            return sympy.Integer(1)  # 假装化简不出 0

        monkeypatch.setattr(sympy, "simplify", _fake_simplify)
        outcome = check_derivative_inverse(
            "求 $f(x) = x^2$ 的导数", "", "导数为 $f'(x) = 2x$"
        )
        assert outcome is not None and outcome[0] == "uncertain"

    def test_none_without_derivative_keyword(self):
        assert check_derivative_inverse("解方程 $x^2 = 9$", "", "$x = 3$") is None


class TestArithmeticChains:
    """算术恒等式验证（提升项 2.1）：真实七年级答案的算术链核对。

    设计要点（真实数据验收定稿）：不匹配一律 uncertain 绝不 failed——
    输入常是教师参考答案（定义正确）+ 公式图丢失后的残缺文本。
    """

    def test_integer_chain_correct_verified(self):
        """全角等号 + 七数连加 + 等式链（真实学生数据原样样本）。"""
        from backend.services.math_verifier import verify_answer

        result = verify_answer("", "", "解：22+40+58+42+26+44+62＝294＝7×42")
        assert result.status == "verified"
        assert "arithmetic_chains" in result.methods
        assert "2 条" in result.details

    def test_integer_chain_mismatch_uncertain_never_failed(self):
        from backend.services.math_verifier import verify_answer

        result = verify_answer("", "", "解：22+40+58+42+26+44+62＝296")
        assert result.status == "uncertain"
        assert "应为 294" in result.details
        assert "人工确认" in result.details

    def test_decimal_chain_exact_verified(self):
        from backend.services.math_verifier import verify_answer

        result = verify_answer("", "", "解：3.14×8×2＝50.24")
        assert result.status == "verified"

    def test_decimal_chain_small_deviation_uncertain(self):
        from backend.services.math_verifier import verify_answer

        result = verify_answer("", "", "解：3.14×8×2＝50.3")
        assert result.status == "uncertain"
        assert "舍入" in result.details

    def test_leading_negative_chain_verified(self):
        """负号开头段（真实数据 #83 的单行形态：-8+16=8）。"""
        from backend.services.math_verifier import verify_answer

        result = verify_answer("", "", "解：原式＝-8+16＝8")
        assert result.status == "verified"
        assert "1 条" in result.details

    def test_cross_line_never_chained(self):
        """跨行不拼链（真实数据 #83/#95 误判根因）：上一步尾+下一步头
        不得拼成跨步恒等式——各行无完整链时返回 None。"""
        from backend.services.math_verifier.arithmetic_verifier import (
            check_arithmetic_chains,
        )

        # 若跨行拼接会得到 4×4=-8+16=8 的假恒等式；单行内无完整链 → None
        assert check_arithmetic_chains("", "", "原式＝4×4\n＝-8+16\n＝8") is None
        assert check_arithmetic_chains("", "", "(-2)×2\n＝-9+4-3+6-4\n＝-6") is None

    def test_variable_substring_rejected(self):
        """变量表达式子串不得成链（真实数据 #66：m-1+1 里的 1+1=2+2）。"""
        from backend.services.math_verifier.arithmetic_verifier import (
            check_arithmetic_chains,
        )

        assert check_arithmetic_chains("", "", "m-1+1=2+2，a=-3") is None

    def test_variable_equations_skipped(self):
        """含字母的等式不归本方法管（解代入的领地）：无链 → None。"""
        from backend.services.math_verifier.arithmetic_verifier import (
            check_arithmetic_chains,
        )

        assert check_arithmetic_chains("", "", "解：x+3=7，所以 x=4") is None
        assert check_arithmetic_chains("", "", "答案 16") is None


class TestNumericVerifier:
    def test_identity_holds(self):
        x = sympy.Symbol("x")
        assert numeric_equation_holds((x + 1) ** 2, x ** 2 + 2 * x + 1, "x") is True

    def test_identity_fails(self):
        x = sympy.Symbol("x")
        assert numeric_equation_holds(x, x + 1, "x") is False

    def test_multivariate_returns_none(self):
        x, y = sympy.symbols("x y")
        assert numeric_equation_holds(x + y, x - y, "x") is None

    def test_constant_sides(self):
        assert numeric_equation_holds(sympy.Integer(0), sympy.Integer(0), "x") is True
        assert numeric_equation_holds(sympy.Integer(1), sympy.Integer(2), "x") is False


class TestVerifyAnswerOrchestration:
    def test_verified_end_to_end(self):
        result = verify_answer("解方程 $x^2 = 9$", "", "解得 $x = \\pm 3$")
        assert result.status == "verified"
        assert "solution_substitution" in result.methods

    def test_failed_priority_over_uncertain(self):
        result = verify_answer("解方程 $x^2 = 9$", "", "解得 $x = 5$")
        assert result.status == "failed"
        assert "残差" in result.details

    def test_uncertain_when_no_math_structure(self):
        result = verify_answer("请默写圆周率前五位", "", "3.14159")
        assert result.status == "uncertain"

    def test_verifier_exception_swallowed(self, monkeypatch):
        """单个验证器崩溃不影响编排（继续尝试其余验证器）。"""
        def _boom(*_args):
            raise RuntimeError("verifier down")

        monkeypatch.setattr(
            answer_verifier,
            "_VERIFIERS",
            (("raising", _boom),) + answer_verifier._VERIFIERS[1:],
        )
        result = verify_answer("求 $f(x) = x^2$ 的导数", "", "导数为 $f'(x) = 2x$")
        assert result.status == "verified"
        assert "derivative_inverse" in result.methods
