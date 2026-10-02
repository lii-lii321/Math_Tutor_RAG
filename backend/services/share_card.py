"""错题分享卡片：把一道错题渲染为适合朋友圈/群聊转发的精美 PNG。

版式：浅灰画布上浮一张圆角白卡（带投影），内含品牌行、难度/知识点胶囊标签、
题面（可选原图嵌入）、「先想一想，再对答案」分隔语、答案面板与品牌页脚。
所有内容自动断行并限量截断，卡片高度自适应但始终保持在适合转发的范围内。
"""
from __future__ import annotations

import datetime as dt
import io
import os

from PIL import Image, ImageDraw

from backend.utils.logging import get_logger

logger = get_logger("share_card")

_CARD_W = 1080
_MARGIN = 44  # 画布四周留白
_PAD = 44  # 卡片内边距
_INNER_W = _CARD_W - 2 * _MARGIN - 2 * _PAD
_MAX_BODY_LINES = 16
_MAX_ANSWER_LINES = 10
_MAX_IMAGE_H = 520

_COLORS = {
    "canvas": "#eef2f7",
    "shadow": "#d9e0ea",
    "card": "#ffffff",
    "border": "#e2e8f0",
    "title": "#1a365d",
    "text": "#334155",
    "muted": "#94a3b8",
    "accent": "#2563eb",
    "soft": "#eff6ff",
    "pill_bg": "#eff6ff",
    "pill_fg": "#2563eb",
    "pill_border": "#bfdbfe",
    "hard_bg": "#1a365d",
    "hard_fg": "#ffffff",
}

_DIFFICULTY_STYLE = {
    "easy": ("pill_bg", "pill_fg", "pill_border"),
    "medium": ("pill_bg", "pill_fg", "pill_border"),
    "hard": ("hard_bg", "hard_fg", "hard_bg"),
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


def _strip_markdown(text: str) -> str:
    for token in ("###", "**", "$$", "$", "`", "#"):
        text = text.replace(token, "")
    return text


def _pill(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    font,
    *,
    bg: str,
    fg: str,
    border: str,
) -> tuple[int, int]:
    """画一枚胶囊标签，返回 (结束 x, 底部 y)。"""
    pad_x, pad_y = 18, 8
    text_w = draw.textlength(text, font=font)
    w = text_w + 2 * pad_x
    h = font.size + 2 * pad_y
    x, y = xy
    draw.rounded_rectangle(
        [x, y, x + w, y + h], radius=h // 2, fill=bg, outline=border, width=1
    )
    draw.text((x + pad_x, y + pad_y - 2), text, font=font, fill=fg)
    return x + w, y + h


def _pill_rows(
    draw: ImageDraw.ImageDraw,
    items: list[tuple[str, dict]],
    font,
    start_y: int,
) -> int:
    """把多枚胶囊按行排布（自动换行），返回排布后的底部 y。"""
    x = _MARGIN + _PAD
    y = start_y
    row_h = 0
    for text, style in items:
        text_w = draw.textlength(text, font=font)
        w = text_w + 36
        h = font.size + 16
        if x + w > _CARD_W - _MARGIN - _PAD and x > _MARGIN + _PAD:
            y += row_h + 12
            x = _MARGIN + _PAD
            row_h = 0
        _pill(draw, (x, y), text, font, **style)
        x += w + 12
        row_h = max(row_h, h)
    return y + row_h


def _load_question_image(question) -> Image.Image | None:
    from backend.utils.paths import resolve_image_path

    path = resolve_image_path(getattr(question, "image_path", None))
    if not path or not path.exists():
        return None
    try:
        with Image.open(path) as img:
            return img.convert("RGB")
    except Exception as exc:  # noqa: BLE001 - 图片损坏不阻断分享
        logger.warning("分享卡片读取题图失败: %s", exc)
        return None


def _pill_style(keys: tuple[str, str, str]) -> dict:
    bg, fg, border = keys
    return {"bg": _COLORS[bg], "fg": _COLORS[fg], "border": _COLORS[border]}


def render_share_card(question, base_url: str = "") -> io.BytesIO:
    """渲染错题分享卡片，返回 PNG 字节流。"""
    draw_probe = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    font_brand = _font(26)
    font_title = _font(46, bold=True)
    font_meta = _font(24)
    font_body = _font(30)
    font_small = _font(22)
    font_hint = _font(24)

    content = _strip_markdown(question.content_markdown or "").strip() or "（无题面）"
    content_lines = _wrap(draw_probe, content, font_body, _INNER_W)
    if len(content_lines) > _MAX_BODY_LINES:
        content_lines = content_lines[:_MAX_BODY_LINES] + ["……（完整解析见应用内）"]
    answer_lines = _wrap(
        draw_probe, _strip_markdown(question.answer or "—"), font_body, _INNER_W - 48
    )
    if len(answer_lines) > _MAX_ANSWER_LINES:
        answer_lines = answer_lines[:_MAX_ANSWER_LINES] + ["……"]

    # 胶囊：难度 + 标签 + 知识点
    tag_style = _pill_style(("pill_bg", "pill_fg", "pill_border"))
    pills: list[tuple[str, dict]] = [
        (question.difficulty, _pill_style(_DIFFICULTY_STYLE.get(question.difficulty, _DIFFICULTY_STYLE["medium"])))
    ]
    pills += [(t, tag_style) for t in (question.tags or [])[:4]]
    pills += [(f"考点 · {k}", tag_style) for k in (question.knowledge_points or [])[:2]]

    question_image = _load_question_image(question)
    image_h = 0
    image_draw = None
    if question_image is not None:
        ratio = min(_INNER_W / question_image.width, _MAX_IMAGE_H / question_image.height, 1.0)
        new_size = (
            max(1, int(question_image.width * ratio)),
            max(1, int(question_image.height * ratio)),
        )
        image_draw = question_image.resize(new_size)
        image_h = new_size[1] + 16

    # ---- 高度测算 ----
    body_h = 44 * len(content_lines)
    answer_h = 64 + 44 * len(answer_lines) + 24
    pill_rows_h = 0
    x_cursor = _MARGIN + _PAD
    row_h = 0
    for text, _style in pills:
        w = draw_probe.textlength(text, font=font_meta) + 36
        h = font_meta.size + 16
        if x_cursor + w > _CARD_W - _MARGIN - _PAD and x_cursor > _MARGIN + _PAD:
            pill_rows_h += row_h + 12
            x_cursor = _MARGIN + _PAD
            row_h = 0
        x_cursor += w + 12
        row_h = max(row_h, h)
    pill_rows_h += row_h

    header_h = 40 + 66 + 62  # 品牌行 + 标题 + 胶囊区起始留白
    divider_h = 76
    footer_h = 56
    card_h = (
        _PAD
        + header_h
        + pill_rows_h
        + 20
        + body_h
        + image_h
        + divider_h
        + answer_h
        + footer_h
        + _PAD
    )
    canvas_h = card_h + 2 * _MARGIN

    # ---- 绘制 ----
    canvas = Image.new("RGB", (_CARD_W, canvas_h), _COLORS["canvas"])
    draw = ImageDraw.Draw(canvas)

    x0, y0 = _MARGIN, _MARGIN
    x1, y1 = _CARD_W - _MARGIN, _MARGIN + card_h
    draw.rounded_rectangle(
        [x0 + 8, y0 + 14, x1 + 8, y1 + 14], radius=28, fill=_COLORS["shadow"]
    )
    draw.rounded_rectangle([x0, y0, x1, y1], radius=28, fill=_COLORS["card"], outline=_COLORS["border"], width=1)

    px = x0 + _PAD
    y = y0 + _PAD

    # 品牌行：左品牌、右日期
    draw.text((px, y), "MathMaster Edu · 错题卡片", font=font_brand, fill=_COLORS["accent"])
    date_text = (
        question.created_at.strftime("%Y-%m-%d")
        if question.created_at
        else dt.date.today().strftime("%Y-%m-%d")
    )
    date_w = draw.textlength(date_text, font=font_meta)
    draw.text((x1 - _PAD - date_w, y + 4), date_text, font=font_meta, fill=_COLORS["muted"])
    y += 46

    # 标题 + 蓝色小标
    draw.rounded_rectangle([px, y + 6, px + 56, y + 14], radius=4, fill=_COLORS["accent"])
    draw.text((px + 72, y - 6), "今日错题", font=font_title, fill=_COLORS["title"])
    y += 74

    # 胶囊标签
    y = _pill_rows(draw, pills, font_meta, y)
    y += 20

    # 题面
    for line in content_lines:
        draw.text((px, y), line, font=font_body, fill=_COLORS["text"])
        y += 44
    y += image_h

    # 分隔语
    y += 8
    draw.line([px, y, x1 - _PAD, y], fill=_COLORS["border"], width=1)
    y += 16
    hint = "— 先想一想，再对答案 —"
    hint_w = draw.textlength(hint, font=font_hint)
    draw.text((( _CARD_W - hint_w) / 2, y), hint, font=font_hint, fill=_COLORS["muted"])
    y += 52

    # 答案面板
    panel_h = answer_h
    draw.rounded_rectangle(
        [px, y, x1 - _PAD, y + panel_h], radius=16, fill=_COLORS["soft"], outline=_COLORS["pill_border"], width=1
    )
    draw.text((px + 24, y + 18), "答案", font=font_meta, fill=_COLORS["accent"])
    ay = y + 64
    for line in answer_lines:
        draw.text((px + 24, ay), line, font=font_body, fill=_COLORS["text"])
        ay += 44
    y += panel_h + 26

    # 页脚
    footer = "让错题变成得分点 · MathMaster Edu"
    draw.text((px, y), footer, font=font_small, fill=_COLORS["muted"])

    # 题图嵌入（画在题面与分隔语之间预留的位置）
    if image_draw is not None:
        img_y = y0 + _PAD + header_h + pill_rows_h + 20 + body_h
        draw.rounded_rectangle(
            [px - 2, img_y - 2, px + image_draw.width + 2, img_y + image_draw.height + 2],
            radius=10,
            fill="#ffffff",
            outline=_COLORS["border"],
            width=1,
        )
        canvas.paste(image_draw, (px, img_y))

    stream = io.BytesIO()
    canvas.save(stream, "PNG")
    stream.seek(0)
    return stream
