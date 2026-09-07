"""错题本：关键词 + 语义双路检索、编辑、批量管理、Word 导出。"""
from __future__ import annotations

import os

import streamlit as st

from backend.services.export import generate_word_exam
from backend.services.question_service import sanitize_tags
from frontend.common import get_question_service, page_header


def render_notebook_page(user: dict) -> None:
    service = get_question_service()
    page_header("错题本", "支持关键词与语义搜索；教师可查看全部学生错题")

    with st.container(border=True):
        col_search, col_tag, col_export = st.columns([3, 2, 1])
        with col_search:
            keyword = st.text_input(
                "搜索",
                placeholder="例如：判别式没掌握的题 / 相似三角形（自然语言即可）",
            )
            semantic = st.toggle("语义搜索", value=True, help="用向量检索理解语义，而非仅字面匹配")
        with col_tag:
            all_questions = service.list_questions(
                user["id"], include_others=user["role"] == "teacher", semantic=False
            )
            all_tags = sorted({t for q in all_questions for t in q.tags})
            tag_filter = st.selectbox("按标签筛选", ["全部"] + all_tags)
        with col_export:
            st.markdown("<br>", unsafe_allow_html=True)

        questions = service.list_questions(
            user["id"],
            include_others=user["role"] == "teacher",
            tag=None if tag_filter == "全部" else tag_filter,
            keyword=keyword or None,
            semantic=semantic,
        )

        st.markdown("<br>", unsafe_allow_html=True)
        if questions:
            doc_io = generate_word_exam(questions, "错题复习卷")
            st.download_button(
                "导出 Word 复习卷",
                data=doc_io,
                file_name="错题复习卷.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                use_container_width=True,
                type="primary",
            )

    if not questions:
        st.info("没有匹配的错题。上传错题图片或调整筛选条件试试。")
        return

    st.caption(f"共 {len(questions)} 题")
    selected_ids: list[int] = []
    for q in questions:
        expander_title = f"{'、'.join(q.tags[:4]) or '未分类'}　·　{q.difficulty}　·　{(q.created_at.strftime('%Y-%m-%d') if q.created_at else '')}"
        with st.expander(expander_title):
            _render_question_detail(service, q, user)
            if st.checkbox("选中", key=f"select_{q.id}"):
                selected_ids.append(q.id)

    if selected_ids:
        st.warning(f"已选中 {len(selected_ids)} 题")
        if st.button("批量删除选中错题", type="primary"):
            service.delete_questions(selected_ids, user["id"])
            st.success(f"已删除 {len(selected_ids)} 题")
            st.rerun()


def _render_question_detail(service, q, user) -> None:
    tab_view, tab_edit = st.tabs(["查看", "编辑"])
    with tab_view:
        img_col, content_col = st.columns([2, 3])
        with img_col:
            if q.image_path and os.path.exists(q.image_path):
                st.image(q.image_path, use_container_width=True)
            else:
                st.caption("无原图（手动录入）")
            badges = " ".join(f"<span class='mm-badge'>{t}</span>" for t in q.tags)
            st.markdown(
                f"<div><span class='mm-badge mm-badge--blue'>{q.difficulty}</span>{badges}</div>",
                unsafe_allow_html=True,
            )
            if q.reps:
                st.caption(f"已复习 {q.reps} 次 · 间隔 {q.interval_days:.0f} 天 ·难度系数 {q.ease:.2f}")
            else:
                st.caption("尚未复习")
        with content_col:
            st.markdown(q.content_markdown, unsafe_allow_html=True)
            if q.answer:
                st.markdown(f"**答案**：{q.answer}")
            if q.followup_question:
                with st.expander("举一反三 · 变式练习"):
                    st.markdown(q.followup_question)

    with tab_edit:
        with st.form(f"edit_form_{q.id}"):
            new_tags = st.text_input("标签（逗号分隔）", value="、".join(q.tags) if q.tags else "")
            new_content = st.text_area("解析（Markdown）", value=q.content_markdown, height=260)
            new_answer = st.text_input("答案", value=q.answer)
            if st.form_submit_button("保存修改", type="primary"):
                service.update_question(
                    q.id,
                    user["id"],
                    content_markdown=new_content,
                    answer=new_answer,
                    tags=sanitize_tags(new_tags.replace("、", ",")),
                )
                st.success("已保存，向量索引同步更新")
                st.rerun()
