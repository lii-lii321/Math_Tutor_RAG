"""学情看板：统计卡、知识点分布、掌握度排行、活跃度趋势。"""
from __future__ import annotations

import plotly.express as px
import streamlit as st

from frontend.common import get_question_service, page_header, provider_badges, stat_card

_BLUE = "#2563eb"

_MASTERY_COLORS = {"weak": "#d97706", "mid": "#2563eb", "good": "#059669"}


def mastery_color(mastery: float) -> str:
    if mastery < 0.4:
        return _MASTERY_COLORS["weak"]
    if mastery < 0.75:
        return _MASTERY_COLORS["mid"]
    return _MASTERY_COLORS["good"]


def render_dashboard(user: dict) -> None:
    service = get_question_service()
    stats = service.dashboard_stats(user["id"], include_others=user["role"] == "teacher")

    st.markdown(
        f"""
        <div class="mm-welcome">
            <h1>你好，{user['username']}</h1>
            <p>今天有 {stats['due']} 道错题等待复习 · 保持节奏，把每一道错题变成得分点。</p>
            <div style="margin-top:0.8rem">{provider_badges()}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        stat_card(stats["total"], "累计错题", accent=True)
    with col2:
        stat_card(len(stats["tag_stats"]), "涉及知识点")
    with col3:
        stat_card(stats["reviewed"], "已复习错题")
    with col4:
        stat_card(stats["due"], "待复习", accent=True)

    st.markdown("<br>", unsafe_allow_html=True)

    chart_col, weak_col = st.columns([3, 2])
    with chart_col:
        page_header("知识点分布", "错题按标签聚合，识别薄弱板块")
        if stats["tag_stats"]:
            top = stats["tag_stats"][:8]
            pie = px.pie(
                names=[s.tag for s in top],
                values=[s.count for s in top],
                hole=0.55,
            )
            pie.update_traces(textposition="outside", textinfo="label+value")
            pie.update_layout(
                showlegend=False,
                margin=dict(t=30, b=20, l=20, r=20),
                height=360,
                paper_bgcolor="rgba(0,0,0,0)",
                font=dict(family="sans-serif", color="#334155"),
            )
            st.plotly_chart(pie, use_container_width=True, config={"displayModeBar": False})
        else:
            st.info("还没有错题，去「AI 录题」上传第一张错题图片吧。")

    with weak_col:
        page_header("薄弱知识点", "按掌握度升序，建议优先复习")
        if stats["weak_tags"]:
            for tag_stat in stats["weak_tags"]:
                color = mastery_color(tag_stat.mastery)
                st.markdown(
                    f"""
                    <div class="mm-mastery">
                        <div class="mm-mastery__row">
                            <span>{tag_stat.tag} <span class="mm-muted">({tag_stat.count} 题)</span></span>
                            <span>{int(tag_stat.mastery * 100)}%</span>
                        </div>
                        <div class="mm-mastery__track">
                            <div class="mm-mastery__fill" style="width:{max(tag_stat.mastery * 100, 3)}%;background:{color}"></div>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
        else:
            st.caption("复习几道题后，这里会生成掌握度分析。")

    st.markdown("<br>", unsafe_allow_html=True)
    page_header("近 14 天录入趋势")
    activity = stats["activity"]
    bar = px.bar(
        x=[a["date"] for a in activity],
        y=[a["count"] for a in activity],
        labels={"x": "日期", "y": "新增错题"},
    )
    bar.update_traces(marker_color=_BLUE)
    bar.update_layout(
        margin=dict(t=10, b=20, l=20, r=20),
        height=260,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="sans-serif", color="#334155"),
        xaxis=dict(type="category", showgrid=False),
        yaxis=dict(dtick=1, range=[0, max(3, max(a["count"] for a in activity) + 1)], gridcolor="#e2e8f0"),
    )
    st.plotly_chart(bar, use_container_width=True, config={"displayModeBar": False})
