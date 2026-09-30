"""学生总览（教师专属）：班级管理 + 全班错题与复习情况一目了然。"""
from __future__ import annotations

import datetime as dt

import streamlit as st

from backend.services.class_service import ClassService
from frontend.common import get_question_service, go_to, page_header
from frontend.components import mastery_bar_html


def _fmt_time(value: dt.datetime | None) -> str:
    if value is None:
        return "—"
    if value.tzinfo is None:
        value = value.replace(tzinfo=dt.timezone.utc)
    delta = dt.datetime.now(dt.timezone.utc) - value
    days = delta.days
    if days <= 0:
        return "今天"
    if days == 1:
        return "昨天"
    if days < 30:
        return f"{days} 天前"
    return f"{days // 30} 个月前"


def _render_class_manager(teacher_id: int, class_service: ClassService, name_to_id: dict[str, int]) -> None:
    """班级管理：建班 / 加学生 / 移出 / 删班（教师专属）。"""
    with st.expander("🏫 班级管理", expanded=not class_service.list_for_teacher(teacher_id)):
        st.caption("建班后，「学生总览」与教师检索范围自动收紧为你所教班级的学生。")
        classes = class_service.list_for_teacher(teacher_id)

        new_name = st.text_input("新班级名称", placeholder="例如：高三（2）班", key="class_new_name")
        if st.button("创建班级", type="primary") and new_name.strip():
            try:
                class_service.create_class(teacher_id, new_name)
                st.toast(f"已创建班级「{new_name.strip()}」", icon="🏫")
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))

        if not classes:
            st.caption("还没有班级。创建后即可把学生分组管理。")
            return

        for klass in classes:
            member_ids = set(class_service.class_student_ids(teacher_id, klass["id"]))
            with st.container(border=True):
                head_col, del_col = st.columns([4, 1])
                with head_col:
                    st.markdown(f"**{klass['name']}**　{klass['member_count']} 名学生")
                with del_col:
                    if st.button("删班", key=f"class_del_{klass['id']}"):
                        class_service.delete_class(teacher_id, klass["id"])
                        st.toast("班级已删除", icon="🗑️")
                        st.rerun()

                add_col, rm_col = st.columns(2)
                with add_col:
                    candidates = sorted(name_to_id)
                    picked = st.selectbox(
                        "添加学生",
                        candidates or ["（暂无学生）"],
                        key=f"class_add_sel_{klass['id']}",
                    )
                    if st.button("加入班级", key=f"class_add_btn_{klass['id']}") and candidates:
                        try:
                            class_service.add_student(teacher_id, klass["id"], name_to_id[picked])
                            st.toast(f"已把 {picked} 加入班级", icon="✅")
                            st.rerun()
                        except ValueError as exc:
                            st.error(str(exc))
                with rm_col:
                    id_to_name = {uid: name for name, uid in name_to_id.items()}
                    members = sorted(id_to_name.get(uid, f"#{uid}") for uid in member_ids)
                    target = st.selectbox(
                        "移出学生",
                        members or ["（班级无成员）"],
                        key=f"class_rm_sel_{klass['id']}",
                    )
                    if st.button("移出班级", key=f"class_rm_btn_{klass['id']}") and members:
                        removed = class_service.remove_student(
                            teacher_id, klass["id"], name_to_id.get(target, -1)
                        )
                        if removed:
                            st.toast(f"已把 {target} 移出班级", icon="👋")
                            st.rerun()


def _render_weekly_report(teacher_id: int, class_names: list[str]) -> None:
    """班级周报：选班 + 窗口期，预览 Markdown 并导出 Word（家校闭环）。"""
    from backend.services.weekly_report import (
        WeeklyReportService,
        generate_word_report,
        render_markdown,
    )

    if not class_names:
        return
    with st.expander("📣 班级周报", expanded=False):
        st.caption("聚合窗口期内每个学生的新增错题、复习表现与薄弱知识点，可直接下发家长。")
        col_class, col_days = st.columns(2)
        with col_class:
            class_name = st.selectbox("选择班级", class_names, key="report_class")
        with col_days:
            days = st.selectbox("统计窗口", [7, 14, 30], index=0, key="report_days")
        if st.button("生成周报", type="primary", width="stretch"):
            try:
                classes = {c["name"]: c["id"] for c in class_service_list(teacher_id)}
                report = WeeklyReportService().build(
                    teacher_id, classes[class_name], days=days
                )
                st.session_state["weekly_report"] = report
            except ValueError as exc:
                st.error(str(exc))
        report = st.session_state.get("weekly_report")
        if report:
            st.markdown(render_markdown(report))
            word_io = generate_word_report(report)
            st.download_button(
                "📄 下载 Word 周报",
                data=word_io,
                file_name=f"班级周报_{report['class_name']}_{report['period']['end']}.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                width="stretch",
            )


def class_service_list(teacher_id: int) -> list[dict]:
    """班级列表快捷查询（周报选班用）。"""
    return ClassService().list_for_teacher(teacher_id)


def render_students_page(user: dict) -> None:
    service = get_question_service()
    class_service = ClassService()
    page_header("学生总览", "班级错题量、复习进度与掌握度 · 帮你定位需要关注的学生")

    try:
        rows = service.students_overview(user["id"])
    except PermissionError:
        st.error("仅教师可以查看学生总览。")
        st.stop()

    name_to_id = {r["username"]: r["user_id"] for r in rows}
    classes = class_service.list_for_teacher(user["id"])
    _render_class_manager(user["id"], class_service, name_to_id)
    _render_weekly_report(user["id"], [c["name"] for c in classes])

    # 班级筛选：默认聚焦第一个班级；也可看全部（含未分班学生）
    classes = class_service.list_for_teacher(user["id"])
    if classes:
        options = ["全部学生"] + [c["name"] for c in classes]
        picked_class = st.selectbox("按班级筛选", options, key="overview_class_filter")
        if picked_class != "全部学生":
            klass = next(c for c in classes if c["name"] == picked_class)
            member_ids = set(class_service.class_student_ids(user["id"], klass["id"]))
            rows = [r for r in rows if r["user_id"] in member_ids]
            if not rows:
                st.info(f"「{picked_class}」还没有成员或成员暂无数据。去上方「班级管理」添加学生。")
                return

    if not rows:
        st.info("还没有学生注册。学生注册后这里会自动出现他们的学习概况。")
        return

    total_questions = sum(r["total"] for r in rows)
    total_due = sum(r["due"] for r in rows)
    active_students = len([r for r in rows if r["total"] > 0])
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(
            f"""<div class="mm-stat mm-stat--accent">
            <div class="mm-stat__value">{len(rows)}</div>
            <div class="mm-stat__label">学生总数（活跃 {active_students}）</div></div>""",
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown(
            f"""<div class="mm-stat">
            <div class="mm-stat__value">{total_questions}</div>
            <div class="mm-stat__label">累计错题</div></div>""",
            unsafe_allow_html=True,
        )
    with c3:
        st.markdown(
            f"""<div class="mm-stat">
            <div class="mm-stat__value">{total_due}</div>
            <div class="mm-stat__label">待复习</div></div>""",
            unsafe_allow_html=True,
        )

    st.markdown("<br>", unsafe_allow_html=True)

    table_data = [
        {
            "学生": r["username"],
            "累计错题": r["total"],
            "待复习": r["due"],
            "已复习": r["reviewed"],
            "涉及知识点": r["tags"],
            "平均掌握度": f"{int(r['mastery'] * 100)}%",
            "最近活跃": _fmt_time(r["last_active"]),
        }
        for r in rows
    ]
    st.dataframe(table_data, width="stretch", hide_index=True)

    st.markdown("<br>", unsafe_allow_html=True)
    page_header("逐个查看", "展开学生查看其知识点掌握情况，或直达其错题本视图")

    for r in rows:
        if r["total"] == 0:
            continue
        with st.expander(f"👤 {r['username']} · {r['total']} 题 · 掌握度 {int(r['mastery'] * 100)}%"):
            col_btn, col_info = st.columns([1, 2])
            with col_btn:
                if st.button("查看错题本", key=f"view_{r['user_id']}", width="stretch"):
                    go_to("notebook", student=r["username"])
            with col_info:
                questions = service.list_questions(r["user_id"], semantic=False)
            tag_count: dict[str, int] = {}
            for q in questions:
                for t in q.tags or []:
                    tag_count[t] = tag_count.get(t, 0) + 1
            if not tag_count:
                st.caption("暂无标签数据")
                continue
            for tag, count in sorted(tag_count.items(), key=lambda kv: kv[1], reverse=True)[:10]:
                st.markdown(
                    mastery_bar_html(
                        tag,
                        count / max(tag_count.values()) * 100,
                        right=f"{count} 题",
                    ),
                    unsafe_allow_html=True,
                )
