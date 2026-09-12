"""学生总览（教师专属）：全班错题与复习情况一目了然。"""
from __future__ import annotations

import datetime as dt

import streamlit as st

from frontend.common import get_question_service, page_header


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


def render_students_page(user: dict) -> None:
    service = get_question_service()
    page_header("学生总览", "全班错题量、复习进度与掌握度 · 帮你定位需要关注的学生")

    try:
        rows = service.students_overview(user["id"])
    except PermissionError:
        st.error("仅教师可以查看学生总览。")
        st.stop()

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
            <div class="mm-stat__label">全班累计错题</div></div>""",
            unsafe_allow_html=True,
        )
    with c3:
        st.markdown(
            f"""<div class="mm-stat">
            <div class="mm-stat__value">{total_due}</div>
            <div class="mm-stat__label">全班待复习</div></div>""",
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
    st.dataframe(table_data, use_container_width=True, hide_index=True)

    st.markdown("<br>", unsafe_allow_html=True)
    page_header("逐个查看", "展开学生查看其知识点掌握情况，或直达其错题本视图")
    from frontend.common import go_to

    for r in rows:
        if r["total"] == 0:
            continue
        with st.expander(f"👤 {r['username']} · {r['total']} 题 · 掌握度 {int(r['mastery'] * 100)}%"):
            col_btn, col_info = st.columns([1, 2])
            with col_btn:
                if st.button("查看错题本", key=f"view_{r['user_id']}", use_container_width=True):
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
                    f"""<div class="mm-mastery">
                        <div class="mm-mastery__row">
                            <span>{tag}</span><span>{count} 题</span>
                        </div>
                        <div class="mm-mastery__track">
                            <div class="mm-mastery__fill" style="width:{min(count / max(tag_count.values()) * 100, 100)}%"></div>
                        </div>
                    </div>""",
                    unsafe_allow_html=True,
                )
