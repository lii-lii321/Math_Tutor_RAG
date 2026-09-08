"""错题本：关键词 + 语义双路检索、编辑、批量管理、Word 导出。"""
from __future__ import annotations

import os

import streamlit as st

from backend.services.export import generate_word_exam
from backend.services.question_service import sanitize_tags
from frontend.common import get_question_service, go_to, page_header, pop_params

_PAGE_SIZE = 8


def render_notebook_page(user: dict) -> None:
    service = get_question_service()
    page_header("错题本", "支持关键词与语义搜索；教师可查看全部学生错题")

    incoming = pop_params("tag", "keyword")
    preset_tag = incoming.get("tag")
    preset_keyword = incoming.get("keyword")

    with st.container(border=True):
        col_search, col_tag, col_export = st.columns([3, 2, 1])
        with col_search:
            keyword = st.text_input(
                "搜索",
                value=preset_keyword or "",
                placeholder="例如：判别式没掌握的题 / 相似三角形（自然语言即可）",
                key="notebook_search",
            )
            semantic = st.toggle("语义搜索", value=True, help="用向量检索理解语义，而非仅字面匹配")
        with col_tag:
            all_questions = service.list_questions(
                user["id"], include_others=user["role"] == "teacher", semantic=False
            )
            all_tags = sorted({t for q in all_questions for t in q.tags})
            default_index = (
                (["全部"] + all_tags).index(preset_tag) if preset_tag in all_tags else 0
            )
            tag_filter = st.selectbox(
                "按标签筛选", ["全部"] + all_tags, index=default_index, key="notebook_tag"
            )
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
        st.markdown(
            """
            <div class="mm-empty">
                <div class="mm-empty__icon">🗂️</div>
                <div>没有匹配的错题。</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        c1, c2 = st.columns(2)
        with c1:
            if st.button("📸 去 AI 录题", use_container_width=True):
                go_to("tutor")
        with c2:
            if st.button("清除筛选条件", use_container_width=True):
                st.session_state.pop("notebook_search", None)
                st.session_state.pop("notebook_tag", None)
                st.session_state.pop("notebook_page", None)
                st.rerun()
        return

    # 分页浏览，避免题目多时单页过长
    total = len(questions)
    page_count = (total + _PAGE_SIZE - 1) // _PAGE_SIZE
    page_key = "notebook_page"
    if page_key not in st.session_state:
        st.session_state[page_key] = 0
    st.session_state[page_key] = min(st.session_state[page_key], page_count - 1)
    page_index = st.session_state[page_key]
    page_items = questions[page_index * _PAGE_SIZE : (page_index + 1) * _PAGE_SIZE]

    nav_l, nav_c, nav_r = st.columns([1, 2, 1])
    with nav_l:
        if st.button("← 上一页", disabled=page_index == 0, use_container_width=True):
            st.session_state[page_key] -= 1
            st.rerun()
    with nav_c:
        st.markdown(
            f"<p class='mm-muted' style='text-align:center;margin-top:0.5rem'>"
            f"共 {total} 题 · 第 {page_index + 1} / {page_count} 页</p>",
            unsafe_allow_html=True,
        )
    with nav_r:
        if st.button(
            "下一页 →", disabled=page_index >= page_count - 1, use_container_width=True
        ):
            st.session_state[page_key] += 1
            st.rerun()

    selected_ids: list[int] = []
    for q in page_items:
        expander_title = f"{'、'.join(q.tags[:4]) or '未分类'}　·　{q.difficulty}　·　{(q.created_at.strftime('%Y-%m-%d') if q.created_at else '')}"
        with st.expander(expander_title):
            _render_question_detail(service, q, user)
            if st.checkbox("选中", key=f"select_{q.id}"):
                selected_ids.append(q.id)

    if selected_ids:
        st.warning(f"已选中 {len(selected_ids)} 题")
        act_col1, act_col2, _ = st.columns([1, 1, 2])
        with act_col1:
            if st.button("批量删除选中错题", type="primary"):
                service.delete_questions(selected_ids, user["id"])
                st.success(f"已删除 {len(selected_ids)} 题")
                st.rerun()
        with act_col2:
            selected = [q for q in questions if q.id in set(selected_ids)]
            doc_io = generate_word_exam(selected, "错题精选复习卷")
            st.download_button(
                "导出选中的错题卷",
                data=doc_io,
                file_name="错题精选复习卷.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                use_container_width=True,
            )


def _render_followup_chat(service, q, user) -> None:
    """围绕一道错题的多轮追问对话。历史保存在 session_state，按题隔离。"""
    history_key = f"chat_{q.id}"
    st.session_state.setdefault(history_key, [])

    for message in st.session_state[history_key]:
        with st.chat_message(message["role"], avatar="🧑‍🎓" if message["role"] == "user" else "📘"):
            st.markdown(message["content"])

    if prompt := st.chat_input("哪里没看懂？问老师（例如：为什么判别式要大于等于零）", key=f"chat_input_{q.id}"):
        st.session_state[history_key].append({"role": "user", "content": prompt})
        with st.chat_message("user", avatar="🧑‍🎓"):
            st.markdown(prompt)
        with st.chat_message("assistant", avatar="📘"):
            try:
                reply = service.answer_followup(
                    q.id, user["id"], st.session_state[history_key], prompt
                )
            except Exception as exc:  # noqa: BLE001 - 对话失败不应崩溃页面
                reply = f"⚠️ 讲师暂时不可用：{exc}"
            st.markdown(reply)
        st.session_state[history_key].append({"role": "assistant", "content": reply})
        st.rerun()

    if st.session_state[history_key] and st.button("清空本题对话", key=f"chat_clear_{q.id}"):
        st.session_state[history_key] = []
        st.rerun()


def _render_question_detail(service, q, user) -> None:
    tab_view, tab_chat, tab_edit = st.tabs(["查看", "追问讲题", "编辑"])
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

    with tab_chat:
        _render_followup_chat(service, q, user)

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
