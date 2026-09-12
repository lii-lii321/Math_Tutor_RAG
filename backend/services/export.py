"""导出服务：把错题列表排版为可打印的 Word 复习卷。

mode:
- "redo"    重做版：只保留原图/题面 + 答题留白，不含解析答案
- "detailed" 详解版：含完整解析与答案，适合对照复盘
"""
from __future__ import annotations

import datetime as dt
import io
import os
from typing import Literal

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches, Pt

from backend.models.schemas import QuestionOut

ExportMode = Literal["redo", "detailed"]

_BLANK_LINES_AFTER_QUESTION = 4


def generate_word_exam(
    questions: list[QuestionOut],
    exam_title: str = "错题复习卷",
    mode: ExportMode = "redo",
) -> io.BytesIO:
    doc = Document()
    heading = doc.add_heading(exam_title, level=0)
    heading.alignment = WD_ALIGN_PARAGRAPH.CENTER

    subtitle = doc.add_paragraph(
        f"{'重做版' if mode == 'redo' else '详解版'} · 共 {len(questions)} 题 · "
        f"由 MathMaster Edu 自动生成 · {dt.date.today().strftime('%Y-%m-%d')}"
    )
    subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
    subtitle.runs[0].font.size = Pt(10)

    for idx, question in enumerate(questions, 1):
        meta = doc.add_paragraph()
        run = meta.add_run(
            f"第 {idx} 题　[{question.difficulty}]　{' / '.join(question.tags)}"
        )
        run.bold = True

        if question.image_path and os.path.exists(question.image_path):
            try:
                doc.add_picture(question.image_path, width=Inches(4.2))
            except Exception:  # noqa: BLE001 - 图片损坏不阻断导出
                doc.add_paragraph("(原图缺失)")
        elif not question.image_path:
            body = doc.add_paragraph()
            body.add_run(question.content_markdown[:600])

        if mode == "detailed":
            doc.add_paragraph()
            doc.add_paragraph(question.content_markdown)
            if question.answer:
                answer = doc.add_paragraph()
                answer_run = answer.add_run(f"答案：{question.answer}")
                answer_run.bold = True
            if question.followup_question:
                doc.add_paragraph(f"变式练习：{question.followup_question}")

        doc.add_paragraph("\n" * _BLANK_LINES_AFTER_QUESTION)

    stream = io.BytesIO()
    doc.save(stream)
    stream.seek(0)
    return stream
