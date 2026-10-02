"""能力画像页：知识点掌握度 + 今日自适应复习计划（Batch 04/05）。"""
from __future__ import annotations

import streamlit as st

from frontend.common import get_question_service, go_to, page_header
from frontend.components import mastery_fill_html, safe_call

_STATUS_BADGE = {
    "solid": "mm-badge mm-badge--blue",
    "shaky": "mm-badge mm-badge--warn",
    "weak": "mm-badge mm-badge--bad",
}
_STATUS_ICON = {"solid": "🟦", "shaky": "🟨", "weak": "🟥"}
_FILL_COLOR = {"solid": "#2563eb", "shaky": "#94a3b8", "weak": "#dc2626"}
_RADAR_MAX = 8


def _render_radar(profile) -> None:
    """薄弱知识点雷达图：取掌握度最低的至多 8 个，MUJI 配色。"""
    import plotly.graph_objects as go

    items = profile[:_RADAR_MAX]
    if len(items) < 3:
        return  # 少于 3 个维度雷达图没有信息量
    fig = go.Figure(
        go.Scatterpolar(
            r=[round(item.mastery * 100) for item in items],
            theta=[item.knowledge_point for item in items],
            fill="toself",
            fillcolor="rgba(37, 99, 235, 0.12)",
            line_color="#2563eb",
            name="掌握度%",
        )
    )
    fig.update_layout(
        margin=dict(t=16, b=16, l=40, r=40),
        height=330,
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(family="sans-serif", color="#334155", size=11),
        polar=dict(
            radialaxis=dict(range=[0, 100], gridcolor="#e2e8f0", showticklabels=False),
            angularaxis=dict(gridcolor="#e2e8f0"),
        ),
        showlegend=False,
    )
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})


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

    left, right = st.columns([3, 2], gap="large")

    with left:
        st.subheader("知识点掌握度")
        if not profile:
            st.markdown(
                """<div class="mm-empty">
                <div class="mm-empty__icon">🎯</div>
                还没有知识点数据。<br>录入错题并填写知识点后，这里会生成你的掌握度画像。
                </div>""",
                unsafe_allow_html=True,
            )
        else:
            weak_count = sum(1 for item in profile if item.status != "solid")
            st.caption(f"共 {len(profile)} 个知识点 · 其中 {weak_count} 个待巩固 · 点击「📝」直达该知识点错题")
            _render_radar(profile)
            for item in profile:
                with st.container(border=True):
                    cols = st.columns([4, 2, 2, 1], vertical_alignment="center")
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
                        if st.button("📝", key=f"kp_go_{item.knowledge_point}", help="在错题本中查看"):
                            go_to("notebook", tag=item.knowledge_point)

    with right:
        st.subheader("今日复习计划")
        size = st.slider("计划题数", min_value=3, max_value=20, value=8, step=1)
        plan = service.today_plan(user["id"], size=size)
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
            if st.button("进入复习模式（按今日计划）", type="primary", width="stretch"):
                go_to("review", mode="plan")
