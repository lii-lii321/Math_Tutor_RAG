"""Word (.docx) 文本提取：标题/段落/表格 → Markdown。

用 python-docx 逐元素遍历（保持标题、段落、表格的原始顺序），
输出可直接入库/送 AI 的 Markdown 文本。
"""
from __future__ import annotations

import io

from backend.utils.logging import get_logger

logger = get_logger(__name__)


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
