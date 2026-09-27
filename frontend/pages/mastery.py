"""能力画像页：知识点掌握度 + 今日自适应复习计划（Batch 04/05）。"""
from __future__ import annotations

import streamlit as st

from frontend.common import get_question_service, go_to, page_header

_STATUS_BADGE = {
    "solid": "mm-badge mm-badge--blue",
    "shaky": "mm-badge mm-badge--warn",
    "weak": "mm-badge mm-badge--bad",
}
_STATUS_ICON = {"solid": "🟦", "shaky": "🟨", "weak": "🟥"}


def _mastery_bar(mastery: float) -> str:
    """单条掌握度横条：MUJI 配色（蓝→灰→红），纯 CSS 无动画。"""
    pct = round(mastery * 100)
    color = "#2563eb" if mastery >= 0.7 else ("#94a3b8" if mastery >= 0.4 else "#dc2626")
    return (
        f'<div style="background:#e2e8f0;border-radius:4px;height:8px;width:100%">'
        f'<div style="background:{color};border-radius:4px;height:8px;width:{pct}%"></div></div>'
    )


def render_mastery_page(user: dict) -> None:
    service = get_question_service()
    page_header(
        "能力画像",
        "知识点掌握度引擎 · 基于复习日志的时间加权评估，自动生成今日加固计划",
    )

    profile = service.mastery_profile(user["id"])

    left, right = st.columns([3, 2], gap="large")

    with left:
        st.subheader("知识点掌握度")
        if not profile:
            st.info("还没有知识点数据：录入错题并填写知识点后，这里会生成你的掌握度画像。")
        else:
            weak_count = sum(1 for item in profile if item.status != "solid")
            st.caption(
                f"共 {len(profile)} 个知识点 · 其中 {weak_count} 个待巩固"
            )
            for item in profile:
                with st.container(border=True):
                    cols = st.columns([5, 2, 2], vertical_alignment="center")
                    with cols[0]:
                        st.markdown(f"**{item.knowledge_point}**")
                        st.markdown(_mastery_bar(item.mastery), unsafe_allow_html=True)
                    with cols[1]:
                        st.metric(
                            "掌握度",
                            f"{item.mastery:.0%}",
                            label_visibility="collapsed",
                        )
                    with cols[2]:
                        st.markdown(
                            f'<span class="{_STATUS_BADGE[item.status]}">'
                            f"{_STATUS_ICON[item.status]} {item.status_label}</span>",
                            unsafe_allow_html=True,
                        )
                        st.caption(f"{item.question_count} 题 · {item.due_count} 题到期")

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
                            go_to("review", question_id=item.question.id)
            if st.button("进入复习模式", type="primary", width="stretch"):
                go_to("review")
