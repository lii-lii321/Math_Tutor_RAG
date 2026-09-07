from __future__ import annotations

import pydantic
import pytest

from backend.services.ai.base import AIMessageError, parse_analysis
from backend.services.ai.mock import MockProvider

VALID = {
    "knowledge_points": ["判别式"],
    "analysis": "先写出判别式表达式，再解不等式。" ,
    "answer": "k ≤ 1/2",
    "difficulty": "medium",
    "tags": ["方程"],
    "mistake_cause": "忽略取等条件",
    "followup_question": "变式题",
}


def test_parse_pure_json():
    import json

    analysis = parse_analysis(json.dumps(VALID, ensure_ascii=False))
    assert analysis.answer == "k ≤ 1/2"


def test_parse_fenced_json():
    import json

    fenced = f"```json\n{json.dumps(VALID, ensure_ascii=False)}\n```"
    analysis = parse_analysis(fenced)
    assert analysis.knowledge_points == ["判别式"]


def test_parse_json_with_surrounding_text():
    import json

    noisy = f"好的，以下是解析结果：\n{json.dumps(VALID, ensure_ascii=False)}\n希望对你有帮助"
    analysis = parse_analysis(noisy)
    assert analysis.mistake_cause == "忽略取等条件"


def test_parse_invalid_json_raises():
    with pytest.raises(AIMessageError):
        parse_analysis("完全不是 JSON 的回复")


def test_parse_python_dict_repr_is_rejected():
    # 模型若输出 Python 字典字面量（单引号）而非 JSON，应触发重试而非静默接受
    with pytest.raises(AIMessageError):
        parse_analysis(str(VALID))


def test_parse_invalid_difficulty_falls_to_validation_error():
    import json

    bad = dict(VALID, difficulty="超难")
    with pytest.raises(pydantic.ValidationError):
        parse_analysis(json.dumps(bad, ensure_ascii=False))


def test_merged_tags_dedup_and_order():
    from backend.models.schemas import QuestionAnalysis

    analysis = QuestionAnalysis(
        knowledge_points=["几何"],
        analysis="这是一段足够长的解析文本，超过最短限制。",
        answer="42",
        tags=["几何", "三角形"],
    )
    merged = analysis.merged_tags(["三角形", "几何", "用户标签"])
    assert merged == ["三角形", "几何", "用户标签"]


def test_mock_provider_returns_valid_analysis():
    provider = MockProvider()
    raw = provider._complete(b"fake-image", "image/jpeg", "prompt")
    analysis = parse_analysis(raw)
    assert analysis.knowledge_points
    info = provider.provider_info()
    assert info.demo_mode is True
