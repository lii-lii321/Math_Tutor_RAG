"""错题本：关键词 + 语义双路检索、编辑、批量管理、Word 导出。"""
from __future__ import annotations

import datetime as dt
import os

import streamlit as st

from backend.services.export import generate_word_exam
from backend.services.question_service import sanitize_tags
from frontend.common import followup_chat, get_question_service, go_to, page_header, pop_params

_PAGE_SIZE = 8


def render_notebook_page(user: dict) -> None:
    service = get_question_service()
    page_header("错题本", "支持关键词与语义搜索；教师可查看全部学生错题")

    incoming = pop_params("tag", "keyword", "student")
    preset_tag = incoming.get("tag")
    preset_keyword = incoming.get("keyword")
    preset_student = incoming.get("student")

    with st.container(border=True):
        is_teacher = user["role"] == "teacher"

        col_search, col_tag, col_export = st.columns([3, 2, 2])
        with col_search:
            keyword = st.text_input(
                "搜索",
                value=preset_keyword or "",
                placeholder="例如：判别式没掌握的题 / 相似三角形（自然语言即可）",
                key="notebook_search",
            )
            semantic = st.toggle("语义搜索", value=True, help="用向量检索理解语义，而非仅字面匹配")
        with col_tag:
            if is_teacher:
                overview = service.students_overview(user["id"])
                student_names = ["全部学生"] + [r["username"] for r in overview]
                default_student = preset_student if preset_student in student_names else "全部学生"
                student_name = st.selectbox(
                    "查看学生", student_names,
                    index=student_names.index(default_student),
                    key="notebook_student",
                )
                if student_name == "全部学生":
                    # 教师视角：全部 = 自己 + 所有学生的题
                    view_user_id = user["id"]
                    include_others = True
                else:
                    view_user_id = next(
                        (r["user_id"] for r in overview if r["username"] == student_name),
                        user["id"],
                    )
                    include_others = False
            else:
                view_user_id = user["id"]
                include_others = False

            all_questions = service.list_questions(
                view_user_id, include_others=include_others, semantic=False
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
            view_user_id,
            include_others=include_others,
            tag=None if tag_filter == "全部" else tag_filter,
            keyword=keyword or None,
            semantic=semantic,
        )

        st.markdown("<br>", unsafe_allow_html=True)
        if questions:
            exp_col1, exp_col2 = st.columns(2)
            with exp_col1:
                redo_io = generate_word_exam(questions, "错题复习卷", mode="redo", answer_key=True)
                st.download_button(
                    "导出重做版（原图+留白+卷末答案）",
                    data=redo_io,
                    file_name=f"错题复习卷_重做版_{dt.date.today():%Y%m%d}.docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    use_container_width=True,
                    type="primary",
                    help="只含题目与答题留白，卷末附参考答案，适合打印重做",
                )
            with exp_col2:
                detail_io = generate_word_exam(questions, "错题详解卷", mode="detailed")
                st.download_button(
                    "导出详解版（含解析答案）",
                    data=detail_io,
                    file_name=f"错题详解卷_{dt.date.today():%Y%m%d}.docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    use_container_width=True,
                    help="含完整解析、答案与变式练习",
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
    now = dt.datetime.now(dt.timezone.utc)
    for q in page_items:
        due_at = q.due_at
        if due_at is not None and due_at.tzinfo is None:
            due_at = due_at.replace(tzinfo=dt.timezone.utc)
        if q.mastered:
            due_mark = "🏆 "
        elif due_at is None or due_at <= now:
            due_mark = "⏰ "
        else:
            due_mark = "✅ "
        expander_title = (
            f"{due_mark}{'、'.join(q.tags[:4]) or '未分类'}　·　{q.difficulty}　·　"
            f"{(q.created_at.strftime('%Y-%m-%d') if q.created_at else '')}"
        )
        with st.expander(expander_title):
            _render_question_detail(service, q, user)
            if st.checkbox("选中", key=f"select_{q.id}"):
                selected_ids.append(q.id)

    if selected_ids:
        st.warning(f"已选中 {len(selected_ids)} 题")
        act_col1, act_col2, act_col3 = st.columns([1, 1.4, 1.6])
        with act_col1:
            if st.button("批量删除选中错题", type="primary"):
                service.delete_questions(selected_ids, user["id"])
                st.toast(f"已删除 {len(selected_ids)} 题", icon="🗑️")
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
        with act_col3:
            new_tag = st.text_input(
                "追加标签", placeholder="例如：月考重点", key="batch_tag"
            )
            if st.button("为选中追加标签", use_container_width=True) and new_tag.strip():
                changed = service.add_tags_to_many(
                    selected_ids, user["id"], sanitize_tags(new_tag)
                )
                st.toast(f"已为 {changed} 题追加标签", icon="🏷️")
                st.rerun()


def _render_followup_chat(service, q, user) -> None:
    """历史保存在 session_state，按题隔离（组件实现在 common）。"""
    followup_chat(service, q, user)


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
            if q.user_note:
                st.info(f"📝 我的笔记：{q.user_note}")
            st.markdown(q.content_markdown, unsafe_allow_html=True)
            if q.answer:
                st.markdown(f"**答案**：{q.answer}")
            if q.followup_question:
                with st.expander("举一反三 · 变式练习"):
                    st.markdown(q.followup_question)
            st.markdown("<br>", unsafe_allow_html=True)
            st.markdown("**重测本题**")
            grade_cols = st.columns(4)
            _grade_labels = {"again": "😵 忘了", "hard": "😅 勉强", "good": "🙂 记得", "easy": "😎 秒懂"}
            for col, grade in zip(grade_cols, ("again", "hard", "good", "easy"), strict=False):
                with col:
                    if st.button(_grade_labels[grade], key=f"nb_grade_{q.id}_{grade}", use_container_width=True):
                        updated = service.grade_review(q.id, user["id"], grade)
                        if updated is None:
                            st.toast("只能重测自己的错题", icon="⚠️")
                        else:
                            st.toast("已按 SM-2 重新排期", icon="🔁")
                        st.rerun()

    with tab_chat:
        _render_followup_chat(service, q, user)

    with tab_edit:
        with st.form(f"edit_form_{q.id}"):
            new_tags = st.text_input("标签（逗号分隔）", value="、".join(q.tags) if q.tags else "")
            new_content = st.text_area("解析（Markdown）", value=q.content_markdown, height=260)
            new_answer = st.text_input("答案", value=q.answer)
            new_note = st.text_area(
                "我的笔记（易错点、思路备忘）",
                value=q.user_note or "",
                height=80,
                placeholder="例如：下次先看第二问的隐藏条件",
            )
            if st.form_submit_button("保存修改", type="primary"):
                updated = service.update_question(
                    q.id,
                    user["id"],
                    content_markdown=new_content,
                    answer=new_answer,
                    tags=sanitize_tags(new_tags.replace("、", ",")),
                    user_note=new_note.strip() or None,
                )
                if updated is None:
                    st.error("保存失败：只能编辑自己的错题（教师可查看但不可修改学生的题）")
                else:
                    st.success("已保存，向量索引同步更新")
                    st.rerun()
