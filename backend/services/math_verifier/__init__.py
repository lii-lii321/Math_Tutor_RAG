"""数学答案验证引擎：SymPy 符号验证 + 数值代入 + 结构化结果。"""
from backend.services.math_verifier.answer_verifier import verify_answer
from backend.services.math_verifier.models import VerificationResult

__all__ = ["VerificationResult", "verify_answer"]
