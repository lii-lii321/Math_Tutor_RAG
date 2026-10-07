"""Anki 牌组导出（.apkg，提升路线批 G 收官项）。

- deck_id / model_id 为固定随机 int：Anki 端按 id 合并，重复导出更新
  同一牌组/模型而非堆积；
- note guid = sha256(content|answer) 指纹（与完整备份 _fingerprint 同源）——
  内容不变重导出即更新原卡，内容变化才生成新卡；
- 正面：原图优先（经 storage materialize，local/S3 双后端同路径；缺失
  回退剥除 Markdown 的题面前 220 字）；背面 = 解析 + 答案 + 标签；
- 空列表 ValueError；genanki 为 requirements.txt 硬依赖，惰性 import
  仅作旧环境防御（缺失时报错含 pip 安装提示）。
"""
from __future__ import annotations

import io
from pathlib import Path

from backend.models.schemas import QuestionOut
from backend.services.full_backup import _fingerprint
from backend.utils.logging import get_logger
from backend.utils.text import strip_markdown

logger = get_logger("anki_export")

# 固定随机 id：Anki 按 id 合并 Deck/Model，保证重导出更新而非新建
_DECK_ID = 1607392319001
_MODEL_ID = 1607392319002
_FRONT_FALLBACK_CHARS = 220
_MODEL_NAME = "MathMaster 错题卡（问答题）"


def generate_anki_deck(
    questions: list[QuestionOut], *, deck_name: str = "MathMaster 错题本"
) -> io.BytesIO:
    """错题列表 → Anki 牌组 .apkg（正面原图/题面，背面解析+答案+标签）。"""
    if not questions:
        raise ValueError("没有可导出的错题")
    try:
        import genanki
    except ImportError as exc:  # 旧环境防御：硬依赖缺失给明确安装提示
        raise RuntimeError(
            "Anki 导出需要 genanki：pip install genanki"
        ) from exc

    model = genanki.Model(
        _MODEL_ID,
        _MODEL_NAME,
        fields=[{"name": "Front"}, {"name": "Back"}],
        templates=[
            {
                "name": "问答题",
                "qfmt": "{{Front}}",
                "afmt": "{{FrontSide}}<hr id=answer>{{Back}}",
            }
        ],
    )
    deck = genanki.Deck(_DECK_ID, deck_name)
    package = genanki.Package(deck)
    media_files: list[str] = []

    for question in questions:
        media_path = _materialize_front_image(question.image_path)
        if media_path is not None:
            media_files.append(media_path)
            front = f'<img src="{Path(media_path).name}">'
        else:
            front = strip_markdown(
                question.content_markdown[:_FRONT_FALLBACK_CHARS]
            ).strip()
        back = _build_back(question)
        note = genanki.Note(
            model=model,
            fields=[front, back],
            guid=genanki.guid_for(_fingerprint(question.content_markdown, question.answer or "")),
        )
        deck.add_note(note)

    package.media_files = media_files
    stream = io.BytesIO()
    package.write_to_file(stream)
    stream.seek(0)
    logger.info("Anki 牌组已生成：%s 题（含图 %s 张）", len(questions), len(media_files))
    return stream


def _materialize_front_image(image_path: str | None) -> str | None:
    """经存储后端 materialize 取原图本地路径（local/S3 双后端同路径）。

    缺失/不可读返回 None（回退题面文字，不阻断导出）。
    """
    if not image_path:
        return None
    from backend.services.storage import get_storage

    path = get_storage().materialize(image_path.replace("\\", "/"))
    return str(path) if path is not None else None


def _build_back(question: QuestionOut) -> str:
    explanation = strip_markdown(question.content_markdown).strip()
    parts = [explanation or "（无解析）", f"<b>答案</b>：{question.answer or '—'}"]
    if question.tags:
        parts.append(f"<i>标签</i>：{'、'.join(question.tags[:6])}")
    return "<br>".join(parts)
