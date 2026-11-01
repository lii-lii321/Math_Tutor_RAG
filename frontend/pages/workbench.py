"""教师工作台：以「今天该做什么」为核心的操作驾驶舱（教师专属）。

与学生总览（报表视角）互补：这里回答的是「现在有什么要处理」——
到期/拖期复习、干预与复测窗口、最近动态与快捷入口。
数据全部来自 TeacherWorkbenchService 聚合（只读）。
"""
from __future__ import annotations

import datetime as dt

import streamlit as st

from backend.services.workbench import TeacherWorkbenchService
from frontend.common import empty_state, go_to, page_header, stat_card
from frontend.components import mastery_bar_html, safe_call


def _fmt_active(value: dt.datetime | None) -> str:
    if value is None:
        return "—"
    if value.tzinfo is None:
        value = value.replace(tzinfo=dt.timezone.utc)
    delta = dt.datetime.now(dt.timezone.utc) - value
    if delta.days <= 0:
        return "今天"
    if delta.days == 1:
        return "昨天"
    if delta.days < 30:
        return f"{delta.days} 天前"
    return f"{delta.days // 30} 个月前"


def _render_onboarding() -> None:
    """未建班引导：三步把工作台跑起来。"""
    empty_state("🏫", "还没有创建班级——工作台还没有可跟踪的学生。")
    st.caption("三步把工作台跑起来：")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("**① 建班加学生**")
        st.caption("学生总览 → 班级管理：建班、把已注册的学生加入班级")
    with c2:
        st.markdown("**② 录入错题**")
        st.caption("AI 录题拍照/Word 导入，或学生自己账号录入")
    with c3:
        st.markdown("**③ 回到工作台**")
        st.caption("到期复习、干预复测、最近动态会自动出现在这里")
    b1, b2 = st.columns(2)
    with b1:
        if st.button("去学生总览建班", type="primary", width="stretch"):
            go_to("students")
    with b2:
        if st.button("去 AI 录题", width="stretch"):
            go_to("tutor")


def _render_interventions(data: dict) -> None:
    totals = data["totals"]
    if not data["interventions"]:
        st.caption("暂无进行中的教学干预。在学生能力画像页点「🎯」开启：诊断 → 练习 → 复测。")
        return
    for item in data["interventions"]:
        window = item["window"]
        tone = "mm-badge mm-badge--bad" if window.startswith("复测已逾期") else (
            "mm-badge mm-badge--warn" if window else "mm-badge mm-badge--blue"
        )
        with st.container(border=True):
            head, action = st.columns([4, 1.2], vertical_alignment="center")
            with head:
                badges = f'<span class="{tone}">{window or "进行中"}</span> '
                st.markdown(
                    f"{badges}<strong>{item['student']}</strong> · {item['knowledge_point']}",
                    unsafe_allow_html=True,
                )
            with action:
                if st.button("看 TA 的题", key=f"wb_iv_{item['id']}", width="stretch"):
                    go_to("notebook", student=item["student"], kp=item["knowledge_point"])
    if totals["retest_due"]:
        st.caption("⏳ 复测通过才计入掌握归档——带学生到能力画像页完成复测登记。")


def render_workbench_page(user: dict) -> None:
    wb = TeacherWorkbenchService()
    ok, data = safe_call(wb.overview, user["id"], error_title="工作台数据加载失败")
    if not ok:
        st.stop()

    today = dt.date.today()
    weekdays = "一二三四五六日"
    page_header(
        "教师工作台",
        f"{today:%m 月 %d 日} · 周{weekdays[today.weekday()]} · 这一屏回答「现在有什么要处理」",
    )

    if not data["has_class"]:
        _render_onboarding()
        return

    totals = data["totals"]
    k1, k2, k3, k4 = st.columns(4)
    with k1:
        stat_card(totals["students"], f"学生（活跃 {sum(1 for s in data['students'] if s['total'] > 0)}）", accent=True)
    with k2:
        stat_card(totals["due"], "待复习（全班）")
    with k3:
        stat_card(totals["overdue"], "拖期超 3 天", accent=totals["overdue"] > 0)
    with k4:
        stat_card(totals["retest_due"], "复测到期", accent=totals["retest_due"] > 0)

    st.markdown("<br>", unsafe_allow_html=True)

    left, right = st.columns([3, 2], gap="large")
    with left:
        st.subheader("学生状态")
        if not data["students"]:
            st.caption("班级还没有成员或成员暂无数据。")
        for row in data["students"]:
            with st.container(border=True):
                head, stat, action = st.columns([4, 2.4, 1.4], vertical_alignment="center")
                with head:
                    flags = ""
                    if row["overdue"]:
                        flags += f'<span class="mm-badge mm-badge--bad">拖期 {row["overdue"]}</span> '
                    if row.get("weak_kps"):
                        flags += f'<span class="mm-badge mm-badge--warn">{row["weak_kps"][0]}</span> '
                    st.markdown(
                        f"<strong>{row['username']}</strong> {flags}",
                        unsafe_allow_html=True,
                    )
                    st.markdown(
                        mastery_bar_html(None, row["mastery"] * 100, right=f"{int(row['mastery'] * 100)}%"),
                        unsafe_allow_html=True,
                    )
                with stat:
                    st.caption(
                        f"错题 {row['total']} · 待复习 {row['due']} · 最近 {_fmt_active(row['last_active'])}"
                    )
                with action:
                    if st.button("看 TA 的题", key=f"wb_st_{row['user_id']}", width="stretch"):
                        go_to("notebook", student=row["username"])

    with right:
        st.subheader("教学干预与复测")
        _render_interventions(data)

        st.divider()
        st.subheader("最近动态")
        if not data["activity"]:
            st.caption("还没有动态。")
        for item in data["activity"]:
            tone = "mm-badge mm-badge--blue" if item["kind"] == "录入" else "mm-badge"
            at = item["at"]
            st.markdown(
                f'<span class="{tone}">{item["kind"]}</span> '
                f"{item['username']} · {_fmt_active(at)} "
                f"<span class='mm-muted'>{item['text']}</span>",
                unsafe_allow_html=True,
            )

    st.divider()
    quick1, quick2, quick3 = st.columns(3)
    with quick1:
        if st.button("📸 去 AI 录题", width="stretch"):
            go_to("tutor")
    with quick2:
        if st.button("📊 学生总览（报表）", width="stretch"):
            go_to("students")
    with quick3:
        if st.button("🗓 看我自己的待复习", width="stretch"):
            go_to("review")
