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
    answer_key: bool = False,
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
            if question.user_note:
                note = doc.add_paragraph()
                note_run = note.add_run(f"我的笔记：{question.user_note}")
                note_run.italic = True
            if question.followup_question:
                doc.add_paragraph(f"变式练习：{question.followup_question}")

        doc.add_paragraph("\n" * _BLANK_LINES_AFTER_QUESTION)

    if answer_key and mode == "redo":
        doc.add_page_break()
        doc.add_heading("参考答案", level=1)
        for idx, question in enumerate(questions, 1):
            answer = doc.add_paragraph()
            run = answer.add_run(f"第 {idx} 题：")
            run.bold = True
            answer.add_run(question.answer or "—")

    stream = io.BytesIO()
    doc.save(stream)
    stream.seek(0)
    return stream


def html_escape(text: str) -> str:
    """HTML 转义并把换行转为 <br/>（reportlab Paragraph 需要）。"""
    import html as _html

    return _html.escape(text).replace("\n", "<br/>")


def generate_pdf_exam(
    questions: list[QuestionOut],
    exam_title: str = "错题复习卷",
    include_answers: bool = True,
) -> io.BytesIO:
    """PDF 复习卷：题目（原图/题面）在前，卷末参考答案。中文用内置 CID 字体。"""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.platypus import Image as RLImage
    from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer

    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    stream = io.BytesIO()

    doc = SimpleDocTemplate(stream, pagesize=A4, title=exam_title, author="MathMaster Edu")
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "CNTitle", parent=styles["Title"], fontName="STSong-Light", fontSize=18
    )
    body_style = ParagraphStyle(
        "CNBody", parent=styles["Normal"], fontName="STSong-Light", fontSize=11, leading=16
    )
    meta_style = ParagraphStyle(
        "CNMeta", parent=body_style, fontSize=9, textColor="#64748b"
    )

    story: list = [
        Paragraph(exam_title, title_style),
        Paragraph(
            f"共 {len(questions)} 题 · MathMaster Edu 生成 · {dt.date.today():%Y-%m-%d}",
            meta_style,
        ),
        Spacer(1, 0.5 * cm),
    ]

    for idx, question in enumerate(questions, 1):
        story.append(
            Paragraph(
                f"<b>第 {idx} 题</b>　[{question.difficulty}]　{' / '.join(question.tags)}",
                body_style,
            )
        )
        if question.image_path and os.path.exists(question.image_path):
            try:
                story.append(RLImage(question.image_path, width=10 * cm, height=7 * cm))
            except Exception:  # noqa: BLE001 - 图片损坏不阻断导出
                story.append(Paragraph("(原图缺失)", body_style))
        else:
            story.append(Paragraph(html_escape(question.content_markdown[:600]), body_style))
        story.append(Spacer(1, 0.8 * cm))

    if include_answers:
        story.append(PageBreak())
        story.append(Paragraph("参考答案", title_style))
        for idx, question in enumerate(questions, 1):
            story.append(
                Paragraph(f"<b>第 {idx} 题：</b>{html_escape(question.answer or '—')}", body_style)
            )
            story.append(Spacer(1, 0.25 * cm))

    doc.build(story)
    stream.seek(0)
    return stream
