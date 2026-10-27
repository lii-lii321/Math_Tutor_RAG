"""Word (.docx) 文本提取：标题/段落/表格 → Markdown。

用 python-docx 逐元素遍历（保持标题、段落、表格的原始顺序），
输出可直接入库/送 AI 的 Markdown 文本。

题号拆分（2026-10-28 真实数据实测后加固）：
- 序列感知：行首题号按「续号/跳号新题、回退号是子题（(1)(2) 小问）」
  处理——此前 (1)(2)(3) 子问会被误拆成空壳题；
- 答案分离：题块内的【答案】/答案：段落抽到 answer 字段（真实错题集
  答案段原样混在题面里导致 questions.answer 全空）；
- 空壳过滤：拆分后正文有效字符过短的块（仅剩编号占位符）由服务层跳过。
"""
from __future__ import annotations

import io
import re

from backend.utils.logging import get_logger

logger = get_logger(__name__)

# 题卡表格：表头行某单元格为「N (客观题) 知识点」——真实错题集（网页导出）
# 每题一个表格，题号与知识点在表头单元格，题干/选项/答案在表体行
_QCARD_HEADER_CELL_RE = re.compile(r"^\s*(\d{1,3})\s*[（(]\s*(客观题|主观题)\s*[）)]\s*(.*)$")
# 拆分用的题卡标题行：## 1 (客观题) 知识点
_QCARD_HEADING_RE = re.compile(
    r"^\s*#{1,6}\s*(\d{1,3})\s*[（(]\s*(?:客观题|主观题)\s*[）)]\s*(.*)$"
)

# 顶层题号模式（可开新题）：1. / 1、 / 1） / 第1题——括号包裹的（1）是小问，不算
_TOP_NUMBER_RE = re.compile(
    r"^\s*(?:第\s*(\d{1,3})\s*题|(\d{1,3})\s*[）).、])\s*\S+"
)
# 小问模式（永不拆分）：（1）/ (1)——真实数据实测：(1)(2)(3) 子问被旧规则误拆成空壳题
_SUB_NUMBER_RE = re.compile(r"^\s*[（(]\s*\d{1,3}\s*[）)]")
# 文末参考答案区：标记行 + 逐题条目「N【原错题参考答案】」
_ANSWER_SECTION_RE = re.compile(r"^\s*【?\s*参考答案\s*】?\s*$")
_ANSWER_ENTRY_RE = re.compile(r"^\s*(\d{1,3})\s*【")

# 答案段标记（行首）：【答案】/答案：/【解答】/解答：
_ANSWER_MARKER_RE = re.compile(r"^\s*(?:【\s*答案\s*】|答案\s*[：:]|【\s*解答\s*】|解答\s*[：:])")
# 答案段终止标记：解析/分析/点拨等讲解段开始
_EXPLANATION_MARKER_RE = re.compile(
    r"^\s*(?:【\s*(?:解析|分析|点拨|思路|评注|方法)\s*】|(?:解析|分析|点拨|思路点拨|方法总结)\s*[：:])"
)
# 标题行（extract_docx_text 输出的 Markdown 标题）
_HEADING_RE = re.compile(r"^\s*#{1,6}\s+(.+?)\s*$")
# 标题里「第N题」式小节头不是知识点
_QUESTION_HEADING_RE = re.compile(r"第\s*\d+\s*题|^\d{1,3}[..、]$")
# 知识点清洗：剥掉标题开头的章节序号（三、/ 12. / (一) / 第3章 等）
_HEADING_ORDINAL_RE = re.compile(
    r"^\s*(?:第\s*[一二三四五六七八九十\d]+\s*[章节单元讲][\s、.．：:]?|[一二三四五六七八九十]{1,3}\s*[、.．]|\d{1,3}\s*[、.．]|[（(]\s*[一二三四五六七八九十\d]+\s*[）)]\s*)"
)


def _match_question_number(para: str) -> int | None:
    """顶层题号行 → 题号数字；小问行与非题号行返回 None。"""
    if _SUB_NUMBER_RE.match(para):
        return None
    qcard = _QCARD_HEADING_RE.match(para)
    if qcard is not None:
        return int(qcard.group(1))
    match = _TOP_NUMBER_RE.match(para)
    if match is None:
        return None
    return int(match.group(1) or match.group(2))


def split_by_question_numbers(text: str) -> list[str] | None:
    """按行首题号做确定性拆分（零 AI 调用）；返回题面文本列表（兼容旧接口）。"""
    structured = split_structured(text)
    if structured is None:
        return None
    return [item["content"] for item in structured]


def split_structured(text: str) -> list[dict] | None:
    """题号结构的完整拆分：每题返回 {content, answer, heading}。

    - 序列感知分组：顶层题号（N. / N、 / N） / 第N题）续号或前跳开新题，
      回退（3→1，答案区重编号）并入当前题块；小问行（（1）/(1)）永不拆分；
    - heading：截至该题块起点的最近章节标题（「第N题」式小节头不算），
      首题之前出现的标题也能继承；
    - answer：题块内【答案】/答案：段分离 + 文末「参考答案」区按
      「N【原错题参考答案】」条目按题号回填（讲解段留在 content）。
    占比防护：新题起点不应占满全文（否则可能只是普通编号列表）。
    """
    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
    if len(paragraphs) < 3:
        return None

    # 文末参考答案区切出：题目区候选不把答案区条目当题号
    section_cut = len(paragraphs)
    for i, para in enumerate(paragraphs):
        if _ANSWER_SECTION_RE.match(para):
            section_cut = i
            break
    body_paragraphs = paragraphs[:section_cut]
    answer_zone = paragraphs[section_cut + 1 :]

    candidates: list[tuple[int, int]] = []  # (body 下标, 题号)
    for i, para in enumerate(body_paragraphs):
        number = _match_question_number(para)
        if number is not None and len(para) >= 6:
            candidates.append((i, number))

    if len(candidates) < 3:
        return None

    # 序列感知分组：回退题号并入当前题块
    groups: list[tuple[int, int, int]] = []  # (起始下标, 截止下标开区间, 题号)
    prev_number: int | None = None
    start: int | None = None
    for pos, (index, number) in enumerate(candidates):
        if prev_number is None or number > prev_number:
            if start is not None:
                groups.append((start, index, candidates[pos - 1][1] if pos else number))
            start = index
        prev_number = number
        if pos == len(candidates) - 1:
            groups.append((start, len(body_paragraphs), number))
    if start is None:
        return None
    # 占比防护：新题起点不应占满全文（否则可能只是普通编号列表）
    if len(groups) > len(body_paragraphs) * 0.8:
        return None

    # 标题按段落流追踪：组起点快照当前标题（含首题之前的标题）
    heading_at: dict[int, str] = {}
    current = ""
    for i, para in enumerate(body_paragraphs):
        qcard = _QCARD_HEADING_RE.match(para)
        if qcard is not None:
            # 题卡标题行的剩余部分就是知识点（已剥离题号与题型标记）
            kp = (qcard.group(2) or "").strip()
            if kp and len(kp) <= 30:
                current = kp
            heading_at[i] = current
            continue
        match = _HEADING_RE.match(para)
        if match:
            text_heading = _HEADING_ORDINAL_RE.sub("", match.group(1).strip()).strip()
            if (
                text_heading
                and not _QUESTION_HEADING_RE.search(text_heading)
                and len(text_heading) <= 30
            ):
                current = text_heading
        heading_at[i] = current

    # 答案区按题号分桶：N【原错题参考答案】条目行开启一桶，其后行入桶
    zone_answers: dict[int, list[str]] = {}
    current_entry: int | None = None
    for para in answer_zone:
        entry = _ANSWER_ENTRY_RE.match(para)
        if entry is not None:
            current_entry = int(entry.group(1))
            zone_answers.setdefault(current_entry, [])
            continue
        if current_entry is not None and para:
            zone_answers[current_entry].append(para)

    items: list[dict] = []
    for begin, end, number in groups:
        part = "\n".join(body_paragraphs[begin:end]).strip()
        if not part:
            continue
        content, inline_answer = separate_answer(part)
        zone_text = "\n".join(zone_answers.get(number, [])).strip()
        answer = zone_text or inline_answer
        items.append(
            {
                "content": content,
                "answer": answer,
                "heading": heading_at.get(begin, ""),
            }
        )
    return items if len(items) >= 2 else None


def separate_answer(part: str) -> tuple[str, str]:
    """从题块中分离答案段：【答案】/答案：起，至下一个讲解标记或块尾。

    返回 (content, answer)；无答案标记时原样返回 (part, "")。
    讲解段（解析/分析/点拨）留在 content——content_markdown 本就是解析讲解。
    """
    lines = part.split("\n")
    answer_start: int | None = None
    for i, line in enumerate(lines):
        if _ANSWER_MARKER_RE.match(line):
            answer_start = i
            break
    if answer_start is None:
        return part, ""

    answer_end = len(lines)
    for j in range(answer_start + 1, len(lines)):
        if _EXPLANATION_MARKER_RE.match(lines[j]):
            answer_end = j
            break

    def _strip_marker(line: str) -> str:
        return re.sub(r"^\s*(?:【\s*答案\s*】|答案\s*[：:]|【\s*解答\s*】|解答\s*[：:])\s*", "", line)

    answer_lines = [_strip_marker(lines[answer_start])]
    answer_lines.extend(lines[answer_start + 1 : answer_end])
    answer = "\n".join(answer_lines).strip()
    content = "\n".join(lines[:answer_start] + lines[answer_end:]).strip()
    if not answer:
        return part, ""
    return content, answer


def content_char_len(content: str) -> int:
    """正文有效字符数：剔除编号、空白与标点后的长度（空壳题检测用）。"""
    cleaned = re.sub(r"[\s，。；：、（）()．.\-—#|／/【】\[\]]", "", content)
    return len(cleaned)


def last_heading(part: str, fallback: str = "") -> str:
    """题块内最后一个 Markdown 标题文本（跨块继承用）；「第N题」式小节头不算。"""
    heading = fallback
    for line in part.split("\n"):
        match = _HEADING_RE.match(line)
        if match:
            text = match.group(1).strip()
            if text and not _QUESTION_HEADING_RE.search(text) and len(text) <= 30:
                heading = text
    return heading


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
        qcell = next((c for c in header if _QCARD_HEADER_CELL_RE.match(c)), None)
        if qcell is not None:
            # 题卡表格：表头 = 题号+题型+知识点，表体 = 题干/选项/答案行
            match = _QCARD_HEADER_CELL_RE.match(qcell)
            assert match is not None  # next() 已过滤
            number, qtype = match.group(1), match.group(2)
            kp = (match.group(3) or "").split("答题时间")[0].strip()
            lines.append(f"## {number} ({qtype}) {kp}".rstrip())
            for row in rows[1:]:
                text = " ".join(c for c in row if c).strip()
                if text.strip("\u200b \t"):
                    lines.append(text.replace("\u200b", ""))
            return
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
