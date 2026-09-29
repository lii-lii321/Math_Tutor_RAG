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
