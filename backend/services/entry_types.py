"""录入结果类型：EntryResult。"""
from __future__ import annotations

from dataclasses import dataclass

from backend.models.schemas import QuestionAnalysis, QuestionOut


@dataclass
class EntryResult:
    """拍照录题的结果：question 为既有记录时 duplicated=True。"""

    question: QuestionOut
    analysis: QuestionAnalysis
    duplicated: bool = False
