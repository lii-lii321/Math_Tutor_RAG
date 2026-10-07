"""文本清理助手（跨服务共用）。"""
from __future__ import annotations


def strip_markdown(text: str) -> str:
    """剥除轻量 Markdown 标记（### 标题、**加粗**、$公式$、`代码`）。

    供纯文本渲染场景使用（分享卡片 PNG、Anki 卡面等）；不做语法树解析，
    仅做与 share_card._strip_markdown 等价的标记替换。
    """
    for token in ("###", "**", "$$", "$", "`", "#"):
        text = text.replace(token, "")
    return text
