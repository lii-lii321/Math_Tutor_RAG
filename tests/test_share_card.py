"""错题分享卡片测试。"""
from __future__ import annotations

import io

from PIL import Image

from backend.models.schemas import QuestionOut
from backend.services.share_card import render_share_card


def _question() -> QuestionOut:
    return QuestionOut(
        id=1,
        user_id=1,
        image_path=None,
        content_markdown="### 题目\n已知 $x^2=9$，求 x 的值。\n### 解析\n开平方得两个解。",
        answer="x=±3",
        tags=["方程", "代数"],
        difficulty="medium",
        created_at=None,
    )


def test_share_card_renders_png():
    stream = render_share_card(_question())
    data = stream.getvalue()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    image = Image.open(io.BytesIO(data))
    assert image.width >= 1000
    assert image.height >= 500  # 卡片有实际内容高度


def test_share_card_handles_long_content():
    question = _question().model_copy(
        update={"content_markdown": "这是一段很长的题面。" * 60, "answer": "长答案" * 30}
    )
    stream = render_share_card(question)
    image = Image.open(stream)
    # 内容更长 → 卡片自动加高，不截断
    short = Image.open(io.BytesIO(render_share_card(_question()).getvalue()))
    assert image.height > short.height
