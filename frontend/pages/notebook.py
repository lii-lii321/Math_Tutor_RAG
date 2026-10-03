"""错题本：关键词 + 语义双路检索、编辑、批量管理、Word 导出。"""
from __future__ import annotations

import datetime as dt

import streamlit as st

from backend.services.comment_service import CommentService
from backend.services.export import generate_pdf_exam, generate_word_exam
from backend.services.mastery import SHAKY_THRESHOLD, WEAK_THRESHOLD
from backend.services.question_service import sanitize_tags
from frontend.common import (
    edit_question_form,
    followup_chat,
    get_question_service,
    go_to,
    page_header,
    pop_params,
)
from frontend.components import (
    question_detail_view,
    regrade_buttons,
    safe_call,
    save_followup_button,
)

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

        # ---- 工具条：搜索框 + 筛选抽屉 + chip 回显 ----
        keyword = st.text_input(
            "搜索",
            value=preset_keyword or "",
            placeholder="搜索错题（自然语言即可）",
            key="notebook_search",
            label_visibility="collapsed",
        )

        # chip 行：当前生效的筛选条件一目了然，点 ✕ 清除
        chips: list[str] = []
        if preset_tag:
            chips.append(preset_tag)
        if preset_keyword:
            chips.append(f"搜索:{preset_keyword}")

        popover_label = "⚙️ 筛选与排序"
        with st.popover(popover_label, use_container_width=False):
            semantic = st.toggle("语义搜索", value=True, help="用向量检索理解语义，而非仅字面匹配")
            only_due = st.toggle("仅看待复习", value=False, help="隐藏已掌握和尚未到期的错题")
            only_mastered = st.toggle("仅看已掌握 🏆", value=False, help="只显示已归档的熟题")
            only_weak = st.toggle(
                "仅看薄弱", value=False, help="只显示复习过且掌握度低于 50% 的题"
            )
            only_starred = st.toggle("⭐ 仅看星标", value=False, help="只显示你收藏的重要错题")
            sort_mode = st.selectbox(
                "排序",
                ["最新录入", "最早录入", "复习次数最少", "最近复习", "掌握度最低"],
                key="notebook_sort",
            )

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

        ok, all_questions = safe_call(
            service.list_questions,
            view_user_id,
            include_others=include_others,
            semantic=False,
            error_title="题库加载失败",
        )
        if not ok:
            st.stop()
        all_tags = sorted({t for q in all_questions for t in q.tags})
        default_index = (
            (["全部"] + all_tags).index(preset_tag) if preset_tag in all_tags else 0
        )
        tag_filter = st.selectbox(
            "按标签筛选", ["全部"] + all_tags, index=default_index, key="notebook_tag"
        )

        # chip 回显：当前生效的筛选条件，点 ✕ 清除
        chips_html = ""
        if preset_tag:
            chips_html += f"<span class='mm-badge mm-badge--blue'>{preset_tag} ✕</span>"
        if preset_keyword:
            chips_html += f"<span class='mm-badge mm-badge--blue'>搜索:{preset_keyword} ✕</span>"
        if only_starred:
            chips_html += "<span class='mm-badge mm-badge--warn'>⭐ 星标</span>"
        if only_weak:
            chips_html += "<span class='mm-badge mm-badge--bad'>薄弱</span>"
        if only_due:
            chips_html += "<span class='mm-badge mm-badge--blue'>待复习</span>"
        if chips_html:
            st.markdown(
                f"<div style='margin:0.3rem 0'>{chips_html}</div>",
                unsafe_allow_html=True,
            )

        ok, questions = safe_call(
            service.list_questions,
            view_user_id,
            include_others=include_others,
            tag=None if tag_filter == "全部" else tag_filter,
            keyword=keyword or None,
            starred=only_starred,
            semantic=semantic,
            error_title="错题检索失败",
        )
        if not ok:
            st.stop()

        def _aware_dt(value: dt.datetime | None) -> dt.datetime:
            return value if value is None or value.tzinfo else value.replace(tzinfo=dt.timezone.utc)

        mastery_map = service.mastery_by_question(view_user_id)
        if only_weak:
            questions = [q for q in questions if mastery_map.get(q.id, 1.0) < 0.5]
        if only_due:
            now_dt = dt.datetime.now(dt.timezone.utc)
            questions = [
                q
                for q in questions
                if q.due_at is None or _aware_dt(q.due_at) <= now_dt
            ]
        if only_mastered:
            questions = [q for q in questions if q.mastered]

        if sort_mode == "最早录入":
            questions.sort(
                key=lambda q: _aware_dt(q.created_at) or dt.datetime.max.replace(tzinfo=dt.timezone.utc)
            )
        elif sort_mode == "复习次数最少":
            questions.sort(key=lambda q: q.reps)
        elif sort_mode == "最近复习":
            questions.sort(
                key=lambda q: _aware_dt(q.last_reviewed_at) or dt.datetime.min.replace(tzinfo=dt.timezone.utc),
                reverse=True,
            )
        elif sort_mode == "掌握度最低":
            questions.sort(key=lambda q: mastery_map.get(q.id, 0.5))

        comment_svc = CommentService()
        total_unread = 0 if include_others else comment_svc.total_unread(user["id"])
        if total_unread:
            st.info(
                f"🔔 你有 **{total_unread}** 条教师新批注未读——带 🔴 标记的题点开「批注」即可查看"
            )

        st.markdown("<br>", unsafe_allow_html=True)
        if questions:
            exp_col1, exp_col2, exp_col3 = st.columns(3)
            with exp_col1:
                redo_io = generate_word_exam(questions, "错题复习卷", mode="redo", answer_key=True)
                st.download_button(
                    "导出重做版（原图+留白+卷末答案）",
                    data=redo_io,
                    file_name=f"错题复习卷_重做版_{dt.date.today():%Y%m%d}.docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    width="stretch",
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
                    width="stretch",
                    help="含完整解析、答案与变式练习",
                )
            with exp_col3:
                pdf_io = generate_pdf_exam(questions, "错题复习卷")
                st.download_button(
                    "导出 PDF（打印友好）",
                    data=pdf_io,
                    file_name=f"错题复习卷_{dt.date.today():%Y%m%d}.pdf",
                    mime="application/pdf",
                    width="stretch",
                    help="题目在前、卷末参考答案，任何设备可打开",
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
            if st.button("📸 去 AI 录题", width="stretch"):
                go_to("tutor")
        with c2:
            if st.button("清除筛选条件", width="stretch"):
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

    unread_map: dict[int, int] = {}
    if not include_others:
        unread_map = comment_svc.unread_counts(user["id"], [q.id for q in page_items])

    nav_l, nav_c, nav_r = st.columns([1, 2, 1])
    with nav_l:
        if st.button("← 上一页", disabled=page_index == 0, width="stretch"):
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
            "下一页 →", disabled=page_index >= page_count - 1, width="stretch"
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
        mastery_chip = ""
        if q.id in mastery_map:
            pct = round(mastery_map[q.id] * 100)
            # 档位与后端掌握度引擎同源（WEAK/SHAKY 阈值换算为百分数）
            if mastery_map[q.id] < WEAK_THRESHOLD:
                color = "#dc2626"
            elif mastery_map[q.id] < SHAKY_THRESHOLD:
                color = "#94a3b8"
            else:
                color = "#2563eb"
            mastery_chip = f"　<span style='color:{color};font-weight:600'>掌握 {pct}%</span>"
        star_mark = "⭐ " if q.starred else ""
        unread = unread_map.get(q.id, 0)
        unread_chip = f"　🔴 <b>{unread} 条新批注</b>" if unread else ""
        expander_title = (
            f"{due_mark}{star_mark}{'、'.join(q.tags[:4]) or '未分类'}　·　{q.difficulty}　·　"
            f"{(q.created_at.strftime('%Y-%m-%d') if q.created_at else '')}"
            f"{mastery_chip}{unread_chip}"
        )
        with st.expander(expander_title):
            _render_question_detail(service, q, user)
            if st.checkbox("选中", key=f"select_{q.id}"):
                selected_ids.append(q.id)

    if selected_ids:
        st.warning(f"已选中 {len(selected_ids)} 题")
        selected = [q for q in questions if q.id in set(selected_ids)]
        act1, act2, act3, act4 = st.columns(4)
        with act1:
            if st.button("🗑️ 批量删除", type="primary", width="stretch"):
                service.delete_questions(selected_ids, user["id"])
                st.toast(f"已删除 {len(selected_ids)} 题", icon="🗑️")
                st.rerun()
        with act2:
            new_diff = st.selectbox(
                "批量改难度",
                ["easy", "medium", "hard"],
                format_func=lambda v: {"easy": "简单", "medium": "中等", "hard": "困难"}[v],
                key="batch_diff",
                label_visibility="collapsed",
            )
            if st.button("应用难度", width="stretch"):
                changed = service.set_difficulty_many(selected_ids, user["id"], new_diff)
                st.toast(f"已把 {changed} 题难度改为 {new_diff}", icon="🎚️")
                st.rerun()
        with act3:
            removable = sorted({t for q in selected for t in (q.tags or [])})
            if not removable:
                st.caption("选中题目暂无标签")
            else:
                rm_tag = st.selectbox("批量移除标签", removable, key="batch_rm_tag", label_visibility="collapsed")
                if st.button("移除该标签", width="stretch"):
                    changed = service.remove_tag_from_many(selected_ids, user["id"], rm_tag)
                    st.toast(f"已从 {changed} 题移除「{rm_tag}」", icon="✂️")
                    st.rerun()
        with act4:
            new_tag = st.text_input(
                "追加标签", placeholder="例如：月考重点", key="batch_tag", label_visibility="collapsed"
            )
            if st.button("为选中追加标签", width="stretch") and new_tag.strip():
                changed = service.add_tags_to_many(
                    selected_ids, user["id"], sanitize_tags(new_tag)
                )
                st.toast(f"已为 {changed} 题追加标签", icon="🏷️")
                st.rerun()

        exp_col1, exp_col2 = st.columns(2)
        with exp_col1:
            redo_io = generate_word_exam(selected, "错题精选复习卷", mode="redo")
            st.download_button(
                "导出选中（重做版）",
                data=redo_io,
                file_name="错题精选复习卷_重做版.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                width="stretch",
            )
        with exp_col2:
            detail_io = generate_word_exam(selected, "错题精选详解卷", mode="detailed")
            st.download_button(
                "导出选中（详解版）",
                data=detail_io,
                file_name="错题精选详解卷.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                width="stretch",
            )


def _share_card_button(q) -> None:
    """生成错题分享卡片 PNG。"""
    from backend.services.share_card import render_share_card

    if st.button("🖼️ 生成分享卡片", key=f"share_{q.id}", width="stretch"):
        stream = render_share_card(q)
        st.download_button(
            "下载分享卡片",
            data=stream,
            file_name=f"错题卡片_{q.id}.png",
            mime="image/png",
            width="stretch",
            key=f"share_dl_{q.id}",
        )


def _render_followup_chat(service, q, user) -> None:
    """历史保存在 session_state，按题隔离（组件实现在 common）。"""
    followup_chat(service, q, user)


def _single_question_export(q) -> None:
    """单题导出：详解版 Word（含原图与答案），方便单独打印或归档。"""
    detail_io = generate_word_exam([q], f"错题详解 · #{q.id}", mode="detailed")
    st.download_button(
        "📄 导出本题 Word（详解版）",
        data=detail_io.getvalue(),
        file_name=f"错题_{q.id}.docx",
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        width="stretch",
    )


def _render_question_detail(service, q, user) -> None:
    tab_view, tab_chat, tab_comment, tab_edit = st.tabs(
        ["查看", "追问讲题", "批注", "编辑"]
    )
    with tab_view:
        if st.button(
            ("⭐ 取消星标" if q.starred else "☆ 加入星标"),
            key=f"star_{q.id}",
            width="stretch",
        ):
            new_state = service.toggle_star(q.id, user["id"])
            if new_state is None:
                st.toast("只能收藏自己的错题", icon="⚠️")
            else:
                st.toast("已加入星标" if new_state else "已取消星标", icon="⭐")
            st.rerun()
        question_detail_view(q)
        if q.followup_question:
            save_followup_button(service, q, user, q.followup_question)
        st.markdown("<br>", unsafe_allow_html=True)
        regrade_buttons(service, q, user)
        _single_question_export(q)
        _share_card_button(q)

    with tab_chat:
        _render_followup_chat(service, q, user)

    with tab_comment:
        _render_comments(q, user)

    with tab_edit:
        edit_question_form(service, q, user)


def _render_comments(q, user) -> None:
    """错题批注：教师批语 / 自己的备注；作者本人或教师可删；打开即清未读红点。"""
    comment_service = CommentService()
    comments = comment_service.list_for_question(q.id)
    if user["id"] == q.user_id:
        # 已读回执：本人打开批注区即视为已读（仅有未读时写入，避免重复落库）
        unread = comment_service.unread_counts(user["id"], [q.id]).get(q.id, 0)
        if unread:
            comment_service.mark_read(q.id, user["id"])
    if comments:
        for comment in comments:
            who = "👨‍🏫" if comment["role"] == "teacher" else "🧑‍🎓"
            st.markdown(
                f"**{who} {comment['author']}**　"
                f"<span class='mm-muted'>"
                f"{comment['created_at'].astimezone().strftime('%m-%d %H:%M') if comment['created_at'] else ''}"
                f"</span>",
                unsafe_allow_html=True,
            )
            st.markdown(comment["content"])
            can_delete = comment["author"] == user["username"] or user["role"] == "teacher"
            if can_delete and st.button("删除", key=f"del_comment_{comment['id']}"):
                comment_service.delete(comment["id"], user["id"], user["role"] == "teacher")
                st.rerun()
            st.divider()
    else:
        st.caption("暂无批注。教师批语和自己的备注都会显示在这里。")

    with st.form(f"comment_form_{q.id}"):
        new_comment = st.text_area("写批注", height=70, placeholder="例如：第二问要注意分类讨论")
        if st.form_submit_button("提交批注", type="primary"):
            if not new_comment.strip():
                st.error("批注内容不能为空")
            else:
                try:
                    comment_service.add(q.id, user["id"], new_comment)
                    st.toast("批注已添加", icon="💬")
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))
