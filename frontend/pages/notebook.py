"""错题本：关键词 + 语义双路检索、编辑、批量管理、Word 导出。"""
from __future__ import annotations

import datetime as dt

import streamlit as st

from backend.services.comment_service import CommentService
from backend.services.export import generate_pdf_exam, generate_word_exam
from backend.services.mastery import SHAKY_THRESHOLD, WEAK_THRESHOLD
from backend.services.question_service import sanitize_tags
from backend.utils.paths import display_image_source
from frontend.common import (
    edit_question_form,
    followup_chat,
    get_question_service,
    go_to,
    page_header,
    pop_params,
)
from frontend.components import (
    mastery_bar_html,
    question_detail_view,
    regrade_buttons,
    safe_call,
    save_followup_button,
)
from frontend.query_state import (
    PARAM_NAMES,
    SORT_OPTIONS,
    STUDENT_DEFAULT,
    TAG_DEFAULT,
    VIEW_OPTIONS,
    WIDGET_KEYS,
    decode_filters,
    encode_filters,
)

_PAGE_SIZE = 8
_DIFF_LABELS = {"easy": "简单", "medium": "中等", "hard": "困难"}


def _current_filters() -> dict:
    """从会话态收集当前生效筛选（控件键缺省时回退默认，供 URL 写回）。"""
    return {
        "keyword": st.session_state.get("notebook_search", ""),
        "tag": st.session_state.get("notebook_tag", TAG_DEFAULT),
        "sort": st.session_state.get("notebook_sort", SORT_OPTIONS[0]),
        "view": st.session_state.get("notebook_view", VIEW_OPTIONS[0]),
        "semantic": st.session_state.get("notebook_sem", True),
        "only_due": st.session_state.get("notebook_due", False),
        "only_mastered": st.session_state.get("notebook_mastered", False),
        "only_weak": st.session_state.get("notebook_weak", False),
        "only_starred": st.session_state.get("notebook_starred", False),
        "student": st.session_state.get("notebook_student", STUDENT_DEFAULT),
        "page": st.session_state.get("notebook_page", 0),
    }


def _write_url_filters() -> None:
    """把当前筛选写回 URL（默认值不写；值未变时零消息，桥接/回调/翻页共用）。"""
    encoded = encode_filters(_current_filters())
    if {
        k: v
        for k, v in st.query_params.to_dict().items()
        if k in PARAM_NAMES
    } == encoded:
        return
    for name in PARAM_NAMES:
        if name in st.query_params:
            del st.query_params[name]
    if encoded:
        st.query_params.update(encoded)


def _clear_url_filters() -> None:
    """清除全部 nb_* URL 参数（清除筛选按钮 / 离开错题本共用）。"""
    for name in PARAM_NAMES:
        if name in st.query_params:
            del st.query_params[name]


def _force_seed(widget_key: str, value) -> None:
    """go_to 桥接参数：实例化前强制覆盖控件会话值（修复二次进入被 key 屏蔽）。"""
    if value is None:
        return
    st.session_state[widget_key] = value


def _seed_if_new(widget_key: str, value, default) -> None:
    """URL 值非默认且控件键尚未入会话时，实例化前种入（刷新/分享/穿登录可达）。"""
    if value is None or value == default or widget_key in st.session_state:
        return
    st.session_state[widget_key] = value


def _due_mark(q, now: dt.datetime) -> str:
    """复习状态图标：🏆 已归档 / ⏰ 到期待复习 / ✅ 已排期。"""
    due_at = q.due_at
    if due_at is not None and due_at.tzinfo is None:
        due_at = due_at.replace(tzinfo=dt.timezone.utc)
    if q.mastered:
        return "🏆"
    if due_at is None or due_at <= now:
        return "⏰"
    return "✅"


def _mastery_parts(mastery_map: dict[int, float], q_id: int) -> tuple[int, str] | None:
    """掌握度 -> (百分数, 档位色)，与后端 WEAK/SHAKY 阈值同源；未复习过返回 None。"""
    if q_id not in mastery_map:
        return None
    ratio = mastery_map[q_id]
    pct = round(ratio * 100)
    if ratio < WEAK_THRESHOLD:
        color = "#dc2626"
    elif ratio < SHAKY_THRESHOLD:
        color = "#94a3b8"
    else:
        color = "#2563eb"
    return pct, color


@st.dialog("错题详情", width="large")
def _open_question_dialog(service, q, user: dict) -> None:
    """卡片视图的详情弹窗（复用列表视图的完整四页签详情）。"""
    _render_question_detail(service, q, user)


def _render_card_grid(
    page_items: list,
    service,
    user: dict,
    mastery_map: dict[int, float],
    unread_map: dict[int, int],
) -> list[int]:
    """卡片网格视图：三列缩略卡（原图 / 元信息徽章 / 掌握度条），查看走弹窗。

    选中复选框与列表视图共用 `select_{id}` 键，切换视图不丢勾选。
    """
    selected_ids: list[int] = []
    now = dt.datetime.now(dt.timezone.utc)
    for start in range(0, len(page_items), 3):
        cols = st.columns(3, gap="small")
        for col, q in zip(cols, page_items[start : start + 3], strict=False):
            with col:
                with st.container(border=True):
                    thumb = display_image_source(q.image_path)
                    if thumb:
                        st.image(thumb, width="stretch")
                    else:
                        label = (q.knowledge_points or q.tags or ["未分类"])[0]
                        st.markdown(
                            f"<div class='mm-card-thumb'>{label[:8]}</div>",
                            unsafe_allow_html=True,
                        )

                    title = "、".join(q.tags[:2]) or "未分类"
                    unread = unread_map.get(q.id, 0)
                    unread_badge = (
                        f" <span class='mm-badge mm-badge--bad'>🔴{unread} 新批注</span>"
                        if unread
                        else ""
                    )
                    star_mark = " ⭐" if q.starred else ""
                    st.markdown(
                        f"<p style='font-weight:600;margin:0.45rem 0 0.3rem;"
                        f"white-space:nowrap;overflow:hidden;text-overflow:ellipsis'>"
                        f"{title}{star_mark}{unread_badge}</p>",
                        unsafe_allow_html=True,
                    )

                    date_txt = q.created_at.strftime("%m-%d") if q.created_at else ""
                    st.markdown(
                        f"<span class='mm-badge'>{_DIFF_LABELS.get(q.difficulty, q.difficulty)}</span>"
                        f"<span class='mm-badge mm-badge--blue'>{_due_mark(q, now)}</span>"
                        f"<span class='mm-badge'>{date_txt}</span>",
                        unsafe_allow_html=True,
                    )

                    parts = _mastery_parts(mastery_map, q.id)
                    if parts is not None:
                        pct, color = parts
                        st.markdown(
                            mastery_bar_html("掌握度", pct, color, right=f"{pct}%"),
                            unsafe_allow_html=True,
                        )
                    else:
                        st.caption("尚未复习")

                    btn_col, sel_col = st.columns([3, 2])
                    with btn_col:
                        if st.button("查看", key=f"card_open_{q.id}", width="stretch"):
                            _open_question_dialog(service, q, user)
                    with sel_col:
                        if st.checkbox("选中", key=f"select_{q.id}"):
                            selected_ids.append(q.id)
    return selected_ids


def _render_list_view(
    page_items: list,
    service,
    user: dict,
    mastery_map: dict[int, float],
    unread_map: dict[int, int],
) -> list[int]:
    """列表视图：expander 逐题展开，标题行带复习/星标/掌握度/未读标记。"""
    selected_ids: list[int] = []
    now = dt.datetime.now(dt.timezone.utc)
    for q in page_items:
        parts = _mastery_parts(mastery_map, q.id)
        mastery_chip = ""
        if parts is not None:
            pct, color = parts
            mastery_chip = (
                f"　<span style='color:{color};font-weight:600'>掌握 {pct}%</span>"
            )
        star_mark = "⭐ " if q.starred else ""
        unread = unread_map.get(q.id, 0)
        unread_chip = f"　🔴 <b>{unread} 条新批注</b>" if unread else ""
        expander_title = (
            f"{_due_mark(q, now)} {star_mark}{'、'.join(q.tags[:4]) or '未分类'}　·　"
            f"{_DIFF_LABELS.get(q.difficulty, q.difficulty)}　·　"
            f"{(q.created_at.strftime('%Y-%m-%d') if q.created_at else '')}"
            f"{mastery_chip}{unread_chip}"
        )
        with st.expander(expander_title):
            _render_question_detail(service, q, user)
            if st.checkbox("选中", key=f"select_{q.id}"):
                selected_ids.append(q.id)
    return selected_ids


def render_notebook_page(user: dict) -> None:
    service = get_question_service()
    page_header("错题本", "支持关键词与语义搜索；教师可查看全部学生错题")

    incoming = pop_params("tag", "keyword", "student")
    url_filters = decode_filters(st.query_params.to_dict())

    # go_to 桥接参数无条件强制覆盖（带选项校验的 tag/student 在各自控件前处理）；
    # URL 参数仅在控件键尚未入会话时种入——刷新 / 分享 / 穿登录可达。
    _force_seed("notebook_search", incoming.get("keyword"))
    _seed_if_new("notebook_search", url_filters["keyword"], "")
    _seed_if_new("notebook_view", url_filters["view"], VIEW_OPTIONS[0])
    _seed_if_new("notebook_sem", url_filters["semantic"], True)
    _seed_if_new("notebook_due", url_filters["only_due"], False)
    _seed_if_new("notebook_mastered", url_filters["only_mastered"], False)
    _seed_if_new("notebook_weak", url_filters["only_weak"], False)
    _seed_if_new("notebook_starred", url_filters["only_starred"], False)
    _seed_if_new("notebook_sort", url_filters["sort"], SORT_OPTIONS[0])
    _seed_if_new("notebook_page", url_filters["page"] or None, None)

    with st.container(border=True):
        is_teacher = user["role"] == "teacher"

        # ---- 工具条：搜索框 + 视图切换 + 筛选抽屉 + chip 回显 ----
        tool_col1, tool_col2 = st.columns([4, 1])
        with tool_col1:
            keyword = st.text_input(
                "搜索",
                placeholder="搜索错题（自然语言即可）",
                key="notebook_search",
                label_visibility="collapsed",
                on_change=_write_url_filters,
            )
        with tool_col2:
            view_mode = st.segmented_control(
                "视图",
                VIEW_OPTIONS,
                selection_mode="single",
                default=VIEW_OPTIONS[0],
                key="notebook_view",
                label_visibility="collapsed",
                on_change=_write_url_filters,
            )
        card_view = view_mode == VIEW_OPTIONS[1]

        popover_label = "⚙️ 筛选与排序"
        with st.popover(popover_label, use_container_width=False):
            semantic = st.toggle(
                "语义搜索",
                value=True,
                help="用向量检索理解语义，而非仅字面匹配",
                key="notebook_sem",
                on_change=_write_url_filters,
            )
            only_due = st.toggle(
                "仅看待复习",
                value=False,
                help="隐藏已掌握和尚未到期的错题",
                key="notebook_due",
                on_change=_write_url_filters,
            )
            only_mastered = st.toggle(
                "仅看已掌握 🏆",
                value=False,
                help="只显示已归档的熟题",
                key="notebook_mastered",
                on_change=_write_url_filters,
            )
            only_weak = st.toggle(
                "仅看薄弱",
                value=False,
                help="只显示复习过且掌握度低于 50% 的题",
                key="notebook_weak",
                on_change=_write_url_filters,
            )
            only_starred = st.toggle(
                "⭐ 仅看星标",
                value=False,
                help="只显示你收藏的重要错题",
                key="notebook_starred",
                on_change=_write_url_filters,
            )
            sort_mode = st.selectbox(
                "排序",
                list(SORT_OPTIONS),
                key="notebook_sort",
                on_change=_write_url_filters,
            )

        if is_teacher:
            overview = service.students_overview(user["id"])
            student_names = ["全部学生"] + [r["username"] for r in overview]
            # 种入值先校验在当前 students_overview 选项内，再于实例化前种入
            bridge_student = incoming.get("student")
            if bridge_student is not None and bridge_student in student_names:
                _force_seed("notebook_student", bridge_student)
            _seed_if_new("notebook_student", url_filters["student"], STUDENT_DEFAULT)
            student_name = st.selectbox(
                "查看学生",
                student_names,
                key="notebook_student",
                on_change=_write_url_filters,
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
        bridge_tag = incoming.get("tag")
        if bridge_tag is not None and bridge_tag in all_tags:
            _force_seed("notebook_tag", bridge_tag)
        _seed_if_new("notebook_tag", url_filters["tag"], TAG_DEFAULT)
        tag_filter = st.selectbox(
            "按标签筛选",
            ["全部"] + all_tags,
            key="notebook_tag",
            on_change=_write_url_filters,
        )
        # 筛选控件全部就位：桥接参数落到 URL、页码钳制自愈（值未变时零消息）
        _write_url_filters()

        # chip 回显：当前生效的筛选条件（实时控件值而非仅 preset，点击 ✕ 走下方清除）
        def _chip(label: str) -> str:
            return f"<span class='mm-badge mm-badge--blue'>{label} ✕</span>"

        chips_html = ""
        if keyword:
            chips_html += _chip(f"搜索:{keyword}")
        if tag_filter != "全部":
            chips_html += _chip(tag_filter)
        if is_teacher and student_name != STUDENT_DEFAULT:
            chips_html += _chip(f"学生:{student_name}")
        if only_starred:
            chips_html += "<span class='mm-badge mm-badge--warn'>⭐ 星标</span>"
        if only_weak:
            chips_html += "<span class='mm-badge mm-badge--bad'>薄弱</span>"
        if only_due:
            chips_html += "<span class='mm-badge mm-badge--blue'>待复习</span>"
        if only_mastered:
            chips_html += "<span class='mm-badge mm-badge--ok'>已掌握</span>"
        if chips_html:
            if st.button("✕ 清除全部筛选", key="clear_chips"):
                for widget_key in WIDGET_KEYS:
                    st.session_state.pop(widget_key, None)
                _clear_url_filters()
                st.rerun()
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
                for widget_key in WIDGET_KEYS:
                    st.session_state.pop(widget_key, None)
                _clear_url_filters()
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
            _write_url_filters()
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
            _write_url_filters()
            st.rerun()

    if card_view:
        # ---- 卡片网格视图（3 列） ----
        selected_ids = _render_card_grid(
            page_items, service, user, mastery_map, unread_map
        )
    else:
        # ---- 列表视图（expander） ----
        selected_ids = _render_list_view(
            page_items, service, user, mastery_map, unread_map
        )

    if selected_ids:
        st.warning(f"已选中 {len(selected_ids)} 题")
        selected = [q for q in questions if q.id in set(selected_ids)]
        act1, act2, act3, act4 = st.columns(4)
        with act1:
            confirm_key = "confirm_delete"
            if st.button("🗑️ 批量删除", type="primary", width="stretch"):
                if st.session_state.get(confirm_key) != selected_ids:
                    # 首次点击：记录选中 ID 并要求二次确认
                    st.session_state[confirm_key] = list(selected_ids)
                    st.warning(f"⚠️ 即将删除 {len(selected_ids)} 题，再次点击确认。")
                    st.stop()
                st.session_state.pop(confirm_key, None)
                service.delete_questions(selected_ids, user["id"])
                st.toast(f"已删除 {len(selected_ids)} 题", icon="🗑️")
                st.rerun()
        with act2:
            new_diff = st.selectbox(
                "批量改难度",
                ["easy", "medium", "hard"],
                format_func=lambda v: _DIFF_LABELS[v],
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
