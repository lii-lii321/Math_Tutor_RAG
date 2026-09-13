"""可复用的展示组件：错题详情视图、重测按钮行。"""
from __future__ import annotations

import os

import streamlit as st

_GRADE_LABELS = {"again": "😵 忘了", "hard": "😅 勉强", "good": "🙂 记得", "easy": "😎 秒懂"}


def question_detail_view(q) -> None:
    """错题「查看」视图：原图/元信息/解析/笔记/答案/变式（不含交互）。"""
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
        if q.followup_question:
            with st.expander("举一反三 · 变式练习"):
                st.markdown(q.followup_question)


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
