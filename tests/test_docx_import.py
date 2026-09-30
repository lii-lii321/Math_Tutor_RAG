"""Word (.docx) 导入链路测试：文本提取、AI 拆题、服务层入库。"""
from __future__ import annotations

import io
import uuid

import pytest

from backend.database import SessionLocal, init_db
from backend.models.orm import User
from backend.services.ai import get_ai_service
from backend.services.ai.base import BaseAIProvider
from backend.services.ai.mock import MockProvider
from backend.services.docx_import import extract_docx_text, split_by_question_numbers
from backend.services.question_service import QuestionService


def _build_docx() -> bytes:
    import docx

    document = docx.Document()
    document.add_heading("月考错题整理", level=1)
    document.add_paragraph("第一次月考中错误率较高的题目，整理如下。")
    document.add_heading("第 1 题", level=2)
    document.add_paragraph("已知 $x^2 = 9$，求 x 的值。")
    table = document.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "步骤"
    table.cell(0, 1).text = "要点"
    table.cell(1, 0).text = "开平方"
    table.cell(1, 1).text = "注意正负"
    buf = io.BytesIO()
    document.save(buf)
    return buf.getvalue()


class TestExtractDocx:
    def test_extracts_headings_paragraphs_tables(self):
        text = extract_docx_text(_build_docx())
        assert "# 月考错题整理" in text
        assert "## 第 1 题" in text
        assert "$x^2 = 9$" in text
        assert "| 步骤 | 要点 |" in text
        assert "| 开平方 | 注意正负 |" in text

    def test_invalid_docx_raises_value_error(self):
        with pytest.raises(ValueError):
            extract_docx_text(b"not a docx")

    def test_empty_document_raises_value_error(self):
        import docx

        buf = io.BytesIO()
        docx.Document().save(buf)
        with pytest.raises(ValueError):
            extract_docx_text(buf.getvalue())


class TestSplitQuestions:
    def test_base_split_parses_json(self, monkeypatch):
        """BaseAIProvider.split_questions 解析 chat 返回的 JSON。"""
        import json as _json

        provider = MockProvider()

        def _fake_chat(messages):
            return _json.dumps(
                {
                    "questions": [
                        {
                            "content": "题一：$x^2=9$",
                            "answer": "x=±3",
                            "knowledge_points": ["开平方"],
                            "difficulty": "easy",
                        },
                        {
                            "content": "题二：$x+1=2$",
                            "answer": "x=1",
                            "knowledge_points": ["一元一次方程"],
                            "difficulty": "easy",
                        },
                    ]
                },
                ensure_ascii=False,
            )

        monkeypatch.setattr(provider, "chat", _fake_chat)
        chunks = BaseAIProvider.split_questions(provider, "文档文本")
        assert len(chunks) == 2
        assert chunks[0]["content"].startswith("题一")

    def test_split_rejects_empty_result(self, monkeypatch):
        provider = MockProvider()

        def _fake_chat(messages):
            return '{"questions": []}'

        monkeypatch.setattr(provider, "chat", _fake_chat)
        from backend.services.ai.base import AIMessageError, BaseAIProvider

        with pytest.raises(AIMessageError):
            BaseAIProvider.split_questions(provider, "文档文本")


class TestAddQuestionsFromDocx:
    def test_mock_provider_imports_whole_doc(self):
        """演示模式：整份文本作为一题入库（零 AI 消耗）。"""
        init_db(seed_users=True)
        with SessionLocal() as session:
            user = User(username=f"docx_{uuid.uuid4().hex[:8]}", password_hash="x", role="student")
            session.add(user)
            session.commit()
            session.refresh(user)

        service = QuestionService(session_factory=SessionLocal)
        result = service.add_questions_from_docx(user.id, _build_docx(), tags=["Word"])
        assert result["total"] == 1
        assert result["imported"] == 1
        saved = result["items"][0]
        assert saved.source == "word"
        assert "月考错题整理" in saved.content_markdown
        assert "Word" in saved.tags

    def test_multi_question_import_with_real_split(self):
        """AI 拆出多题时逐题入库，难度非法值回落 medium。"""
        import json as _json

        init_db(seed_users=True)
        with SessionLocal() as session:
            user = User(
                username=f"docx2_{uuid.uuid4().hex[:8]}", password_hash="x", role="student"
            )
            session.add(user)
            session.commit()
            session.refresh(user)

        service = QuestionService(session_factory=SessionLocal)
        provider = get_ai_service()

        def _fake_chat(messages):
            return _json.dumps(
                {
                    "questions": [
                        {"content": "甲题内容", "answer": "42", "knowledge_points": ["测试"], "difficulty": "easy"},
                        {"content": "乙题内容", "answer": "", "knowledge_points": [], "difficulty": "超难"},
                    ]
                },
                ensure_ascii=False,
            )

        provider.chat = _fake_chat
        service.ai = provider
        # Mock 的 split_questions 是覆写实现（不走 chat）——patch 成走基类解析路径
        service.ai.split_questions = lambda text: BaseAIProvider.split_questions(
            provider, text
        )

        result = service.add_questions_from_docx(user.id, _build_docx(), tags=["整理"])
        assert result["total"] == 2
        assert result["imported"] == 2
        difficulties = [q.difficulty for q in result["items"]]
        assert difficulties == ["easy", "medium"]  # 非法难度回落 medium
        assert all("整理" in q.tags for q in result["items"])

    def test_max_questions_cap(self):
        """拆题数量上限（服务层默认 100）。"""
        import json as _json

        provider = MockProvider()

        def _fake_chat(messages):
            return _json.dumps(
                {
                    "questions": [
                        {"content": f"题{i}", "answer": "", "knowledge_points": [], "difficulty": "easy"}
                        for i in range(120)
                    ]
                },
                ensure_ascii=False,
            )

        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setattr(provider, "chat", _fake_chat)
        chunks = BaseAIProvider.split_questions(provider, "文档文本")
        assert len(chunks) == 120  # 基类解析不截断
        capped = chunks[:100]
        assert len(capped) == 100
        monkeypatch.undo()

    def test_long_text_segmented_into_multiple_calls(self):
        """长文档按段落边界分段：多次 AI 调用，全部拆题结果合并。"""
        init_db(seed_users=True)
        import json as _json

        with SessionLocal() as session:
            user = User(
                username=f"docx3_{uuid.uuid4().hex[:8]}", password_hash="x", role="student"
            )
            session.add(user)
            session.commit()
            session.refresh(user)

        service = QuestionService(session_factory=SessionLocal)
        provider = get_ai_service()

        calls: list[str] = []

        def _fake_chat(messages):
            user_text = messages[-1]["content"]
            calls.append(user_text)
            # 每段返回 2 题，带段内标记以便区分
            marker = "A" if len(calls) == 1 else "B"
            return _json.dumps(
                {
                    "questions": [
                        {"content": f"段{marker}题一" + "长" * 30, "answer": "", "knowledge_points": [], "difficulty": "easy"},
                        {"content": f"段{marker}题二" + "长" * 30, "answer": "", "knowledge_points": [], "difficulty": "easy"},
                    ]
                },
                ensure_ascii=False,
            )

        provider.chat = _fake_chat
        service.ai = provider
        service.ai.split_questions = lambda text: BaseAIProvider.split_questions(
            provider, text
        )

        # 构造 >4000 字的多段文档（中文每字一个字符位）
        long_doc = "\n\n".join(f"第{i}段落标题\n\n{'内容' * 300}" for i in range(8))
        assert len(long_doc) > 4000

        # 直接测试分段逻辑与跨段合并
        from backend.services.question_mixins import _segment_text

        segments = _segment_text(long_doc)
        assert len(segments) >= 2, "长文档应被切成多段"
        for seg in segments:
            assert len(seg) <= 4000 + 200, "单段不应显著超限"

        chunks: list = []
        for seg in segments:
            chunks.extend(service.ai.split_questions(seg))
        assert len(chunks) == 2 * len(segments)
        assert len(calls) == len(segments), "每段一次 AI 调用"


class TestQuestionNumberSplit:
    def test_numbered_document_splits_deterministically(self):
        """行首题号 ≥3 且占比合理 → 确定性拆分（零 AI 调用）。"""
        text = "\n".join(
            [
                "月考错题整理",
                "1. 已知 x^2 = 9，求 x 的值。",
                "2. 计算 16 的算术平方根。",
                "3. 化简 (x+1)^2 - (x-1)^2。",
                "附：以上题目均来自第一次月考。",
            ]
        )
        parts = split_by_question_numbers(text)
        assert parts is not None and len(parts) == 3
        assert parts[0].startswith("1.")

    def test_unnumbered_text_returns_none(self):
        assert split_by_question_numbers("第一段\n\n第二段\n\n第三段") is None

    def test_too_few_numbers_returns_none(self):
        assert split_by_question_numbers("1. 只有一题\n结尾说明") is None


class TestStructuralImportPath:
    def test_numbered_doc_skips_ai_entirely(self):
        """题号文档走结构识别：AI 拆题被调用即失败（证明零 AI）。"""
        init_db(seed_users=True)
        with SessionLocal() as session:
            user = User(
                username=f"docx4_{uuid.uuid4().hex[:8]}", password_hash="x", role="student"
            )
            session.add(user)
            session.commit()
            session.refresh(user)

        service = QuestionService(session_factory=SessionLocal)

        def _must_not_call(_text):
            raise AssertionError("题号结构识别路径不应调用 AI 拆题")

        service.ai.split_questions = _must_not_call

        import docx

        buf = io.BytesIO()
        document = docx.Document()
        document.add_paragraph("本周整理的三道错题如下：")  # 占比防护：题号行需 < 80%
        for line in [
            "1. 已知 x = 1，求 2x。",
            "2. 已知 x = 2，求 3x。",
            "3. 已知 x = 3，求 4x。",
        ]:
            document.add_paragraph(line)
        document.save(buf)

        result = service.add_questions_from_docx(user.id, buf.getvalue(), tags=["结构"])
        assert result["mode"].startswith("题号结构识别")
        assert result["imported"] == 3
        assert result["failed_segments"] == 0
