"""数据备份导出/导入 + 手动录题的服务层测试。"""
from __future__ import annotations

import io

import pytest
from PIL import Image

from backend.database import SessionLocal
from backend.services.question_service import QuestionService


def _tiny_jpeg() -> bytes:
    image = Image.new("RGB", (8, 8), (90, 200, 150))
    stream = io.BytesIO()
    image.save(stream, format="JPEG")
    return stream.getvalue()


@pytest.fixture
def service():
    return QuestionService(session_factory=SessionLocal)


def test_create_manual_question(service, student_user):
    saved = service.create_manual_question(
        student_user.id,
        content_markdown="已知 $a>0$，求证 $a^2 \\ge 0$。",
        answer="显然成立",
        tags=["代数", "不等式"],
        knowledge_points=["基本不等式"],
    )
    assert saved.id > 0
    assert saved.source == "manual"
    assert saved.tags == ["代数", "不等式"]
    assert saved.image_path is None


def test_manual_question_semantic_searchable(service, student_user):
    saved = service.create_manual_question(
        student_user.id,
        content_markdown="鸡兔同笼：共 35 个头 94 只脚，求鸡兔各几只。",
        answer="鸡 23 只，兔 12 只",
        tags=["应用题"],
    )
    results = service.list_questions(student_user.id, keyword="鸡兔同笼")
    assert any(q.id == saved.id for q in results)


def test_export_import_roundtrip(service, student_user):
    saved = service.create_manual_question(
        student_user.id,
        content_markdown="导出测试题目：解方程 $2x=6$。",
        answer="x=3",
        tags=["备份测试"],
    )
    backup = service.export_user_data(student_user.id)
    assert backup["format"] == "mathmaster-backup"
    assert backup["count"] >= 1
    assert any(q["id"] == saved.id for q in backup["questions"])


def test_import_rejects_bad_format(service, student_user):
    with pytest.raises(ValueError):
        service.import_user_data(student_user.id, {"hello": "world"})


def test_import_restores_questions(service, student_user):
    backup = {
        "format": "mathmaster-backup",
        "version": 1,
        "questions": [
            {
                "content_markdown": "导入题目一：$1+1=?$",
                "answer": "2",
                "tags": ["导入"],
                "knowledge_points": ["算术"],
            },
            {"content_markdown": "", "answer": "", "tags": []},  # 空内容应被跳过
        ],
    }
    before = len(service.list_questions(student_user.id, semantic=False))
    imported = service.import_user_data(student_user.id, backup)
    assert imported == 1
    after = service.list_questions(student_user.id, semantic=False)
    assert len(after) == before + 1
    restored = after[0]
    assert restored.source == "imported"
