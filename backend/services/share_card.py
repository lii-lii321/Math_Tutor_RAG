"""错题分享卡片：把一道错题渲染为精美的可分享 PNG。"""
from __future__ import annotations

import io
import os

from PIL import Image, ImageDraw

from backend.utils.logging import get_logger

logger = get_logger("share_card")

_CARD_W = 1080
_MARGIN = 60
_COLORS = {
    "bg": "#ffffff",
    "title": "#1a365d",
    "text": "#334155",
    "muted": "#94a3b8",
    "accent": "#2563eb",
    "soft": "#eff6ff",
    "border": "#e2e8f0",
}


def _font(size: int, bold: bool = False):
    """按平台挑选可用中文字体；找不到则用 PIL 默认（可能不支持中文）。"""
    from PIL import ImageFont

    candidates = [
        r"C:\Windows\Fonts\msyhbd.ttc" if bold else r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\simhei.ttf",
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        "/System/Library/Fonts/PingFang.ttc",
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return ImageFont.load_default(size=size)


def has_cjk_font() -> bool:
    """当前环境是否有可渲染中文的字体（决定测试断言与卡片回退样式）。"""
    return _font(20) is not None and any(
        os.path.exists(p)
        for p in (
            r"C:\Windows\Fonts\msyh.ttc",
            r"C:\Windows\Fonts\simhei.ttf",
            "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
            "/System/Library/Fonts/PingFang.ttc",
        )
    )


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> list[str]:
    """按像素宽度断行（先按换行拆段；中文逐字、英文按词）。"""
    lines: list[str] = []
    for segment in text.split("\n"):
        current = ""
        for ch in segment:
            trial = current + ch
            if draw.textlength(trial, font=font) <= max_width or not current:
                current = trial
            else:
                lines.append(current)
                current = ch
        if current:
            lines.append(current)
    return lines or [""]


def render_share_card(question, base_url: str = "") -> io.BytesIO:
    """渲染错题分享卡片，返回 PNG 字节流。"""
    draw_probe = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    font_title = _font(44, bold=True)
    font_meta = _font(26)
    font_body = _font(30)
    font_small = _font(22)

    content = question.content_markdown or ""
    # 去掉 Markdown 标记，保留纯文本可读性
    for token in ("###", "**", "$$", "$", "`"):
        content = content.replace(token, "")
    content_lines = _wrap(draw_probe, content.strip() or "（无题面）", font_body, _CARD_W - 2 * _MARGIN)
    answer_lines = _wrap(draw_probe, question.answer or "—", font_body, _CARD_W - 2 * _MARGIN)
    footer = "MathMaster Edu · 智能错题本"

    body_h = 34 * len(content_lines) + 24
    answer_h = 34 * len(answer_lines) + 70
    card_h = (
        _MARGIN * 3 + 60 + 44 + body_h + answer_h + 60 + 40
    )

    image = Image.new("RGB", (_CARD_W, card_h), _COLORS["bg"])
    draw = ImageDraw.Draw(image)

    # 顶部品牌条
    draw.rectangle([0, 0, _CARD_W, 10], fill=_COLORS["accent"])
    draw.text((_MARGIN, _MARGIN), "📘 今日错题", font=font_title, fill=_COLORS["title"])
    meta = f"{question.difficulty} · {' / '.join((question.tags or [])[:4])} · {question.created_at:%Y-%m-%d}" if question.created_at else question.difficulty
    draw.text((_MARGIN, _MARGIN + 62), meta, font=font_meta, fill=_COLORS["muted"])

    y = _MARGIN + 130
    for line in content_lines:
        draw.text((_MARGIN, y), line, font=font_body, fill=_COLORS["text"])
        y += 34
    y += 16

    # 答案区块
    draw.rounded_rectangle(
        [_MARGIN, y, _CARD_W - _MARGIN, y + answer_h - 40],
        radius=14,
        fill=_COLORS["soft"],
        outline=_COLORS["border"],
    )
    draw.text((_MARGIN + 24, y + 18), "✅ 答案", font=font_meta, fill=_COLORS["accent"])
    ay = y + 60
    for line in answer_lines:
        draw.text((_MARGIN + 24, ay), line, font=font_body, fill=_COLORS["text"])
        ay += 34

    # 底部
    draw.text((_MARGIN, card_h - _MARGIN - 26), footer, font=font_small, fill=_COLORS["muted"])

    stream = io.BytesIO()
    image.save(stream, "PNG")
    stream.seek(0)
    return stream
