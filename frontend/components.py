"""可复用的展示组件：错题详情视图、重测按钮、变式题入库、命中高亮。"""
from __future__ import annotations

import html
import os

import streamlit as st

_GRADE_LABELS = {"again": "😵 忘了", "hard": "😅 勉强", "good": "🙂 记得", "easy": "😎 秒懂"}


def question_detail_view(q, show_hit: bool = True) -> None:
    """错题「查看」视图：原图/元信息/解析/笔记/答案/变式（不含交互）。

    show_hit：搜索场景下展示关键词命中片段预览。
    """
    img_col, content_col = st.columns([2, 3])
    with img_col:
        if q.image_path and os.path.exists(q.image_path):
            st.image(q.image_path, width="stretch")
        else:
            st.caption("无原图（手动录入）")
        badges = " ".join(f"<span class='mm-badge'>{t}</span>" for t in q.tags)
        st.markdown(
            f"<div><span class='mm-badge mm-badge--blue'>{q.difficulty}</span>{badges}</div>",
            unsafe_allow_html=True,
        )
        if q.reps:
            st.caption(f"已复习 {q.reps} 次 · 间隔 {q.interval_days:.0f} 天 · 难度系数 {q.ease:.2f}")
        else:
            st.caption("尚未复习")
    with content_col:
        if q.user_note:
            st.info(f"📝 我的笔记：{q.user_note}")
        st.markdown(q.content_markdown, unsafe_allow_html=True)
        if q.answer:
            st.markdown(f"**答案**：{q.answer}")
        _hit_preview(q)
        if q.followup_question:
            with st.expander("举一反三 · 变式练习"):
                st.markdown(q.followup_question)


def _hit_preview(q) -> None:
    """展示搜索关键词的首个命中片段（转义后高亮，不改动原解析渲染）。"""
    keyword = st.session_state.get("notebook_search")
    if not keyword:
        return
    kw = keyword.strip()
    if not kw:
        return
    for source in (q.content_markdown, q.answer or "", q.ocr_text or ""):
        lowered = source.lower()
        pos = lowered.find(kw.lower())
        if pos < 0:
            continue
        start = max(0, pos - 30)
        end = min(len(source), pos + len(kw) + 30)
        fragment = source[start:end]
        highlighted = re_escape_and_mark(fragment, kw)
        st.markdown(
            f"🔍 命中：<span style='background:#fef3c7;border-radius:4px'>"
            f"{highlighted}</span>",
            unsafe_allow_html=True,
        )
        return


def re_escape_and_mark(fragment: str, keyword: str) -> str:
    """HTML 转义后高亮关键词（大小写不敏感）。"""
    import re

    escaped_kw = re.escape(keyword)
    marked = re.sub(
        escaped_kw,
        lambda m: f"<mark>{html.escape(m.group(0))}</mark>",
        html.escape(fragment),
        flags=re.IGNORECASE,
    )
    return marked.replace("\n", " ")


def regrade_buttons(service, q, user: dict) -> None:
    """单题重测：按 SM-2 对本题直接评分（教师操作他人题目会得到提示）。"""
    st.markdown("**重测本题**")
    grade_cols = st.columns(4)
    for col, grade in zip(grade_cols, ("again", "hard", "good", "easy"), strict=False):
        with col:
            if st.button(
                _GRADE_LABELS[grade], key=f"nb_grade_{q.id}_{grade}", width="stretch"
            ):
                updated = service.grade_review(q.id, user["id"], grade)
                if updated is None:
                    st.toast("只能重测自己的错题", icon="⚠️")
                else:
                    st.toast("已按 SM-2 重新排期", icon="🔁")
                st.rerun()


def save_followup_button(service, q, user: dict, followup: str) -> None:
    """把变式练习一键存为新的待做错题（继承原题标签并追加「变式练习」）。"""
    if not followup:
        return
    if st.button("📥 把变式题存入错题本", key=f"save_followup_{q.id}"):
        tags = [*(q.tags or []), "变式练习"]
        saved = service.create_manual_question(
            user["id"],
            content_markdown=f"### 变式练习（来自错题 #{q.id}）\n\n{followup}",
            tags=tags,
            source="followup",
        )
        st.success(f"已存入错题本（#{saved.id}），进入正常复习循环。")
