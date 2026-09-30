"""Word (.docx) 文本提取：标题/段落/表格 → Markdown。

用 python-docx 逐元素遍历（保持标题、段落、表格的原始顺序），
输出可直接入库/送 AI 的 Markdown 文本。
"""
from __future__ import annotations

import io
import re

from backend.utils.logging import get_logger

logger = get_logger(__name__)

# 题号模式：1. / 1、 / 1） / 第1题 / （1）等（行首，独立成段）
_QUESTION_NUMBER_RE = re.compile(
    r"^\s*(?:第\s*\d{1,3}\s*题|[（(]?\s*\d{1,3}\s*[）).、])\s*\S+"
)


def split_by_question_numbers(text: str) -> list[str] | None:
    """按行首题号做确定性拆分（零 AI 调用）。

    规则：统计段落中题号开头的行，出现 ≥3 个且递增（允许乱序占少数）才认定
    为题号结构；否则返回 None（交由 AI 拆题）。借鉴 dotty-tutor 的
    「确定性门禁优先于模型」模式。
    """
    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
    if len(paragraphs) < 3:
        return None

    numbered: list[tuple[int, str]] = []
    for i, para in enumerate(paragraphs):
        if _QUESTION_NUMBER_RE.match(para) and len(para) >= 6:
            numbered.append((i, para))

    if len(numbered) < 3:
        return None
    # 题号行不应占满全文（否则可能只是普通编号列表）
    if len(numbered) > len(paragraphs) * 0.8:
        return None

    parts: list[str] = []
    for pos, (start, _) in enumerate(numbered):
        end = numbered[pos + 1][0] if pos + 1 < len(numbered) else len(paragraphs)
        parts.append("\n".join(paragraphs[start:end]).strip())
    parts = [p for p in parts if p]
    return parts if len(parts) >= 2 else None


def extract_docx_text(data: bytes) -> str:
    """从 .docx 字节流提取 Markdown 文本；无法解析时抛 ValueError。"""
    import docx
    from docx.document import Document as _Document
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    try:
        document = docx.Document(io.BytesIO(data))
    except Exception as exc:  # noqa: BLE001 - 损坏的 docx 统一转为用户可读错误
        raise ValueError(f"Word 文档解析失败：{exc}") from exc

    lines: list[str] = []

    def _walk(parent) -> None:
        body = parent.element.body
        for child in body.iterchildren():
            if child.tag.endswith("}p"):
                _emit_paragraph(Paragraph(child, parent))
            elif child.tag.endswith("}tbl"):
                _emit_table(Table(child, parent))

    def _emit_paragraph(paragraph: Paragraph) -> None:
        text = paragraph.text.strip()
        if not text:
            return
        style = (paragraph.style.name or "").lower() if paragraph.style is not None else ""
        if style.startswith("heading 1") or style == "标题 1":
            lines.append(f"# {text}")
        elif style.startswith("heading 2") or style == "标题 2":
            lines.append(f"## {text}")
        elif style.startswith("heading"):
            lines.append(f"### {text}")
        else:
            lines.append(text)

    def _emit_table(table: Table) -> None:
        rows = [[cell.text.strip().replace("\n", " ") for cell in row.cells] for row in table.rows]
        rows = [r for r in rows if any(r)]
        if not rows:
            return
        header = rows[0]
        lines.append("| " + " | ".join(header) + " |")
        lines.append("|" + "---|" * len(header))
        for row in rows[1:]:
            lines.append("| " + " | ".join(row) + " |")

    if not isinstance(document, _Document):
        raise ValueError("Word 文档格式不正确")
    _walk(document)
    text = "\n\n".join(lines).strip()
    if not text:
        raise ValueError("Word 文档内容为空")
    return text
