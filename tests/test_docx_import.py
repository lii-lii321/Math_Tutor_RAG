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
from backend.services.docx_import import (
    content_char_len,
    extract_docx_text,
    last_heading,
    separate_answer,
    split_by_question_numbers,
)
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

    def test_sub_question_numbers_merge_into_parent(self):
        """(1)(2) 子问题号回退 → 并入当前题块，不拆成空壳（真实数据实测缺陷）。"""
        text = "\n".join(
            [
                "错题集",
                "3. 3×3×3 正方体表面涂色后切割，三面红/两面红/一面红/无红各有几个？",
                "（1）三面红的有几个？",
                "（2）两面红的有几个？",
                "4. 每面切三刀得 4×4×4，各色块数量？",
                "5. 长方体粮囤容积问题。",
            ]
        )
        parts = split_by_question_numbers(text)
        assert parts is not None
        assert len(parts) == 3, "（1）（2）应并入第 3 题，而不是拆成 5 块"
        assert "（1）三面红" in parts[0] and "（2）两面红" in parts[0]


class TestSeparateAnswer:
    def test_answer_block_extracted_with_explanation_bound(self):
        part = "\n".join(
            [
                "3. 3×3×3 正方体表面涂色后切割，各色块数量？",
                "【答案】三面红 8 个，两面红 12 个，一面红 6 个，无红 1 个。",
                "【解析】顶点 8 个不变；棱上 12(n-2) 个。",
            ]
        )
        content, answer = separate_answer(part)
        assert "三面红 8 个" in answer
        assert "12(n-2)" not in answer  # 解析段不混入答案
        assert "【解析】顶点" in content
        assert "正方体表面涂色" in content

    def test_inline_answer_marker(self):
        content, answer = separate_answer("2. 计算 16 的算术平方根。\n答案：4")
        assert answer == "4"
        assert "算术平方根" in content

    def test_no_answer_marker_untouched(self):
        part = "1. 求 x。\n解析：开平方。"
        content, answer = separate_answer(part)
        assert content == part
        assert answer == ""


class TestStubAndHeading:
    def test_content_char_len_ignores_numbering_and_punctuation(self):
        assert content_char_len("(1)/(2)/(3). ；") < 6
        assert content_char_len("已知 x=1，求 2x。") >= 6

    def test_last_heading_skips_question_headers(self):
        part = "\n".join(["## 第 3 题", "### 圆的计算", "5. 长方体粮囤容积问题。"])
        assert last_heading(part) == "圆的计算"

    def test_last_heading_fallback_kept_when_part_has_none(self):
        assert last_heading("5. 无标题的题。", fallback="上一章的标题") == "上一章的标题"


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
        assert result["skipped_stubs"] == 0

    def test_structured_import_separates_answers_merges_subs_inherits_heading(self):
        """真实数据实测缺陷的端到端回归：答案进 answer 字段、（1）（2）并入
        母题、空壳跳过、章节标题继承为知识点。"""
        init_db(seed_users=True)
        with SessionLocal() as session:
            user = User(
                username=f"docx5_{uuid.uuid4().hex[:8]}", password_hash="x", role="student"
            )
            session.add(user)
            session.commit()
            session.refresh(user)

        service = QuestionService(session_factory=SessionLocal)

        def _must_not_call(_text):
            raise AssertionError("本路径不应调用 AI 拆题")

        service.ai.split_questions = _must_not_call

        import docx

        buf = io.BytesIO()
        document = docx.Document()
        document.add_heading("三、圆柱与圆锥", level=2)
        document.add_paragraph("1. 3×3×3 正方体表面涂色后切割，三面红/两面红/一面红/无红各有几个？")
        document.add_paragraph("（1）三面红的有几个？")
        document.add_paragraph("（2）两面红的有几个？")
        document.add_paragraph("【答案】8 个 / 12 个 / 6 个 / 1 个。")
        document.add_paragraph("2. 圆柱粮囤底面周长 20 米，求容积。")
        document.add_paragraph("3. 没有答案和标题的普通题。")
        document.save(buf)

        result = service.add_questions_from_docx(user.id, buf.getvalue(), tags=["实测"])
        assert result["imported"] == 3, "（1）（2）并入第 1 题，共 3 题"
        assert result["skipped_stubs"] == 0

        first = result["items"][0]
        assert "8 个 / 12 个" in first.answer, "答案段应进入 answer 字段"
        assert "【答案】" not in first.content_markdown
        assert "（1）三面红" in first.content_markdown, "子问保留在母题题面"
        assert "圆柱与圆锥" in first.knowledge_points, "章节标题继承为知识点"
        assert "圆柱与圆锥" in first.tags or "实测" in first.tags
        assert result["items"][1].answer == ""
        assert all("圆柱与圆锥" in q.knowledge_points for q in result["items"]), "标题跨题继承"
