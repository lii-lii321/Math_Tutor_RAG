"""能力画像页：知识点掌握度 + 今日自适应复习计划 + 教学干预闭环（Batch 04/05）。"""
from __future__ import annotations

import streamlit as st

from backend.services.teaching import TeachingService
from frontend.charts import plotly_font, plotly_grid, semantic_colors
from frontend.common import empty_state, get_question_service, go_to, page_header
from frontend.components import mastery_fill_html, safe_call

_STATUS_BADGE = {
    "solid": "mm-badge mm-badge--blue",
    "shaky": "mm-badge mm-badge--warn",
    "weak": "mm-badge mm-badge--bad",
}
_STATUS_ICON = {"solid": "🟦", "shaky": "🟨", "weak": "🟥"}
# 掌握度横条填充色：与 common.mastery_color / style.css 语义变量同源
# （HTML 内联直用 var(--*)，深色自动翻面；solid 走品牌蓝）
_FILL_COLOR = {"solid": "var(--brand)", "shaky": "var(--shaky)", "weak": "var(--weak)"}
_RADAR_MAX = 8

_STRATEGY_LABEL = {
    "weak_drill": "概念重建 + 基础变式",
    "error_cause": "错因归类 + 针对性变式",
    "maintenance": "保温综合",
}
_OUTCOME_META = {
    "diagnosed": ("🩺 已诊断", "mm-badge mm-badge--blue"),
    "practiced": ("✍️ 练习中", "mm-badge mm-badge--warn"),
    "retest_scheduled": ("⏳ 待复测", "mm-badge mm-badge--warn"),
    "retest_passed": ("🎉 复测通过", "mm-badge mm-badge--ok"),
    "retest_failed": ("🔁 复测未过", "mm-badge mm-badge--bad"),
}
_ACTIVE_OUTCOMES = ("diagnosed", "practiced", "retest_scheduled")


def _render_radar(profile) -> None:
    """薄弱知识点雷达图：取掌握度最低的至多 8 个，MUJI 配色。"""
    import plotly.graph_objects as go

    items = profile[:_RADAR_MAX]
    if len(items) < 3:
        return  # 少于 3 个维度雷达图没有信息量
    brand = semantic_colors()["brand"]
    fig = go.Figure(
        go.Scatterpolar(
            r=[round(item.mastery * 100) for item in items],
            theta=[item.knowledge_point for item in items],
            fill="toself",
            fillcolor="rgba(37, 99, 235, 0.18)",
            line_color=brand,
            name="掌握度%",
        )
    )
    grid = plotly_grid()
    fig.update_layout(
        margin=dict(t=16, b=16, l=40, r=40),
        height=330,
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(**plotly_font(), size=11),
        polar=dict(
            radialaxis=dict(range=[0, 100], gridcolor=grid, showticklabels=False),
            angularaxis=dict(gridcolor=grid),
        ),
        showlegend=False,
    )
    st.plotly_chart(fig, width="stretch", key="chart_radar", config={"displayModeBar": False})


def _render_interventions(user: dict) -> None:
    """教学干预闭环操作区：诊断 → 练习 → 独立作答 → 延迟复测（右栏）。

    数据面全部走 TeachingService（状态机与归属校验见 backend/services/teaching.py）；
    UI 只做状态展示与动作触发，失败统一 error_card 降级。
    """
    teaching = TeachingService()
    ok, history = safe_call(
        teaching.history, user["id"], limit=50, error_title="教学干预记录加载失败"
    )
    if not ok:
        st.stop()
    history = history or []
    active = [row for row in history if row["outcome"] in _ACTIVE_OUTCOMES]
    done = [row for row in history if row["outcome"] not in _ACTIVE_OUTCOMES]

    if not active and not done:
        st.caption(
            "在左侧薄弱知识点点「🎯」开启一次教学干预：诊断 → 针对性练习 → "
            "独立作答 → 7 天后延迟复测，复测通过才计入掌握归档。"
        )
        return

    # 复测题摘要映射：一次拉取当前用户题目（数量个人级，够用）
    q_service = get_question_service()
    snippets: dict[int, str] = {}
    for row in active:
        for qid in row["question_ids"]:
            if qid not in snippets:
                fetched = q_service.get_question(qid, user["id"])
                snippets[qid] = (fetched.content_markdown[:24] if fetched else f"#{qid}")

    for row in active:
        iid = row["id"]
        label, badge_cls = _OUTCOME_META[row["outcome"]]
        with st.container(border=True):
            st.markdown(
                f'<span class="{badge_cls}">{label}</span> '
                f'<span class="mm-badge">{_STRATEGY_LABEL.get(row["strategy"], row["strategy"])}</span>',
                unsafe_allow_html=True,
            )
            st.markdown(f"**{row['knowledge_point']}** · {len(row['question_ids'])} 题")
            if row["outcome"] == "retest_scheduled":
                st.caption(f"约定复测时间：{row['retest_due_at'][:16].replace('T', ' ')}（到期前请独立完成）")
            else:
                st.caption("先独立完成这组练习，再按实际作答情况登记")

            if row["outcome"] in ("diagnosed", "practiced"):
                c1, c2, c3 = st.columns([2, 1.4, 1.4])
                with c1:
                    if st.button("去练习这组题", key=f"ti_practice_{iid}", width="stretch"):
                        go_to("notebook", kp=row["knowledge_point"])
                with c2:
                    if st.button("✅ 作答通过", key=f"ti_pass_{iid}", width="stretch"):
                        ok2, _ = safe_call(
                            _advance_to_outcome, teaching, row, user["id"], True,
                            error_title="作答结果登记失败",
                        )
                        if ok2:
                            st.toast("已约定 7 天后复测——到时回来登记复测结果", icon="⏳")
                            st.rerun()
                with c3:
                    if st.button("😅 作答未通过", key=f"ti_fail_{iid}", width="stretch"):
                        ok2, _ = safe_call(
                            _advance_to_outcome, teaching, row, user["id"], False,
                            error_title="作答结果登记失败",
                        )
                        if ok2:
                            st.toast("已记录：这组题再练一轮后重新登记", icon="🔁")
                            st.rerun()
            else:  # retest_scheduled
                options = row["question_ids"] or []
                if options:
                    fmt = {qid: f"#{qid} {snippets.get(qid, '')}" for qid in options}
                    retest_qid = st.selectbox(
                        "复测题目",
                        options,
                        format_func=lambda q, _fmt=fmt: _fmt[q],
                        key=f"ti_retest_q_{iid}",
                    )
                    c1, c2 = st.columns(2)
                    with c1:
                        if st.button("✅ 复测通过", key=f"ti_rt_pass_{iid}", width="stretch"):
                            ok2, _ = safe_call(
                                teaching.record_retest,
                                iid, user["id"], True, retest_qid,
                                error_title="复测结果登记失败",
                            )
                            if ok2:
                                st.toast("复测通过已记录——该题满足 SM-2 条件时即归档", icon="🎉")
                                st.rerun()
                    with c2:
                        if st.button("❌ 复测未过", key=f"ti_rt_fail_{iid}", width="stretch"):
                            ok2, _ = safe_call(
                                teaching.record_retest,
                                iid, user["id"], False, retest_qid,
                                error_title="复测结果登记失败",
                            )
                            if ok2:
                                st.toast("已记录：题目留在复习池，继续按 SM-2 排期", icon="🔁")
                                st.rerun()

    if done:
        with st.expander(f"已完成干预（{len(done)} 次）"):
            for row in done:
                label, badge_cls = _OUTCOME_META[row["outcome"]]
                st.markdown(
                    f'<span class="{badge_cls}">{label}</span> '
                    f"{row['knowledge_point']} · {(row['created_at'] or '')[:10]}",
                    unsafe_allow_html=True,
                )


def _advance_to_outcome(teaching: TeachingService, row: dict, user_id: int, passed: bool) -> dict:
    """diagnosed 状态先落练习登记（沿用诊断题组），再登记独立作答结果。"""
    if row["outcome"] == "diagnosed":
        teaching.record_practice(row["id"], user_id, row["question_ids"])
    return teaching.record_outcome(row["id"], user_id, passed)


def _start_intervention(teaching: TeachingService, user_id: int, kp: str) -> dict:
    return teaching.start_intervention(user_id, kp)


def render_mastery_page(user: dict) -> None:
    service = get_question_service()
    page_header(
        "能力画像",
        "知识点掌握度引擎 · 基于复习日志的时间加权评估，自动生成今日加固计划",
    )

    ok, profile = safe_call(
        service.mastery_profile,
        user["id"],
        error_title="掌握度数据加载失败",
    )
    if not ok:
        st.stop()
    profile = profile or []

    teaching = TeachingService()
    left, right = st.columns([3, 2], gap="large")

    with left:
        st.subheader("知识点掌握度")
        if not profile:
            empty_state(
                "🎯",
                "还没有知识点数据。录入错题并填写知识点后，这里会生成你的掌握度画像。",
            )
        else:
            weak_count = sum(1 for item in profile if item.status != "solid")
            st.caption(f"共 {len(profile)} 个知识点 · 其中 {weak_count} 个待巩固 · 点击「📝」按知识点筛错题、「🎯」开启教学干预")
            _render_radar(profile)
            for item in profile:
                with st.container(border=True):
                    cols = st.columns([4, 2, 2, 1, 1], vertical_alignment="center")
                    with cols[0]:
                        st.markdown(f"**{item.knowledge_point}**")
                        st.markdown(
                            mastery_fill_html(item.mastery * 100, _FILL_COLOR[item.status]),
                            unsafe_allow_html=True,
                        )
                    with cols[1]:
                        st.markdown(f"**{item.mastery:.0%}**")
                        st.caption("掌握度")
                    with cols[2]:
                        st.markdown(
                            f'<span class="{_STATUS_BADGE[item.status]}">'
                            f"{_STATUS_ICON[item.status]} {item.status_label}</span>",
                            unsafe_allow_html=True,
                        )
                        st.caption(f"{item.question_count} 题 · {item.due_count} 题到期")
                    with cols[3]:
                        if st.button("📝", key=f"kp_go_{item.knowledge_point}", help="在错题本中按该知识点筛选"):
                            go_to("notebook", kp=item.knowledge_point)
                    with cols[4]:
                        if item.status != "solid":
                            if st.button(
                                "🎯",
                                key=f"kp_start_{item.knowledge_point}",
                                help="开启教学干预：诊断→练习→作答→延迟复测",
                            ):
                                ok, _diag = safe_call(
                                    _start_intervention,
                                    teaching, user["id"], item.knowledge_point,
                                    error_title="教学干预开启失败",
                                )
                                if ok:
                                    st.toast(
                                        f"已开启「{item.knowledge_point}」教学干预，见右侧干预区",
                                        icon="🎯",
                                    )
                                    st.rerun()

    with right:
        st.subheader("今日复习计划")
        size = st.slider("计划题数", min_value=3, max_value=20, value=8, step=1)
        ok, plan = safe_call(
            service.today_plan,
            user["id"], size=size,
            error_title="今日计划生成失败",
        )
        if not ok:
            st.stop()
        if not plan:
            st.success("🎉 今日没有需要处理的题目，休息一下。")
        else:
            st.caption(f"已生成 {len(plan)} 题：到期题优先，其余按薄弱知识点加固")
            for i, item in enumerate(plan):
                with st.container(border=True):
                    cols = st.columns([4, 1], vertical_alignment="center")
                    with cols[0]:
                        st.markdown(f"**{i + 1}. {item.question.content_markdown[:40]}**")
                        st.markdown(
                            f"""<div style="margin-bottom:0.2rem">
                            <span class="mm-badge mm-badge--blue">{item.question.difficulty}</span>
                            {''.join(f'<span class="mm-badge">{t}</span>' for t in item.question.tags[:3])}
                            </div>""",
                            unsafe_allow_html=True,
                        )
                        st.caption(item.reason)
                    with cols[1]:
                        if st.button("复习", key=f"plan_go_{item.question.id}", width="stretch"):
                            go_to("review", mode="plan", question_id=item.question.id)
            # primary 纪律（spec §5.3）：本页无 primary，全 secondary
            if st.button("进入复习模式（按今日计划）", width="stretch"):
                go_to("review", mode="plan")

        st.divider()
        st.subheader("🎯 教学干预")
        _render_interventions(user)
