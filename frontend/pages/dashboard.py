"""学情看板 v2：Hero 行动卡 + 待复习队列表格 + 薄弱横条 + 分布/正确率图表。

布局对齐 docs/deck v2 模板：第一屏回答"今天该做什么"，
全部数据来自现有 stats / today_plan / mastery_by_question，无新增后端接口。
"""
from __future__ import annotations

import datetime as dt

import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from backend.config import get_settings
from backend.services.mastery import SHAKY_THRESHOLD, WEAK_THRESHOLD
from frontend.charts import (
    heatmap_colorscale,
)
from frontend.charts import (
    plotly_font as _plotly_font,
)
from frontend.charts import (
    plotly_grid as _plotly_grid,
)
from frontend.charts import (
    plotly_ink as _plotly_ink,
)
from frontend.common import (
    get_question_service,
    go_to,
    mastery_color,
    page_header,
    provider_badges,
    stat_card,
)
from frontend.components import mastery_bar_html, safe_call

_BLUE = "#2563eb"


def _render_difficulty(dist: dict) -> None:
    """难度分布环形图（旧版辅助函数，收进折叠区使用）。"""
    if not dist or sum(dist.values()) == 0:
        st.caption("还没有错题数据。")
        return
    color_map = {"easy": "#93c5fd", "medium": "#2563eb", "hard": "#1a365d"}
    pie = px.pie(
        names=[k for k in dist],
        values=[dist[k] for k in dist],
        hole=0.5,
        color=[k for k in dist],
        color_discrete_map=color_map,
    )
    pie.update_layout(
        showlegend=True,
        margin=dict(t=10, b=10, l=10, r=10),
        height=240,
        paper_bgcolor="rgba(0,0,0,0)",
        font=_plotly_font(),
    )
    st.plotly_chart(pie, width="stretch", key="chart_difficulty", config={"displayModeBar": False})


def _picked_tag(event) -> str | None:
    """从 plotly on_select 事件里取被点击色条/扇区对应的标签。"""
    selection = getattr(event, "selection", None)
    points = getattr(selection, "points", None) if selection else None
    for point in points or []:
        for key in ("y", "label", "customdata", "name"):
            value = point.get(key) if isinstance(point, dict) else getattr(point, key, None)
            if value:
                return str(value[0] if isinstance(value, list) else value)
    return None


def _greeting() -> str:
    hour = dt.datetime.now().hour
    if 5 <= hour < 11:
        return "早上好"
    if 11 <= hour < 14:
        return "中午好"
    if 14 <= hour < 18:
        return "下午好"
    return "晚上好"


def _aware(value: dt.datetime | None) -> dt.datetime | None:
    return value if value is None or value.tzinfo else value.replace(tzinfo=dt.timezone.utc)


def _today_bounds() -> tuple[dt.datetime, dt.datetime]:
    """本地今天的零点与明天零点（aware）。"""
    now_local = dt.datetime.now().astimezone()
    start = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    return start, start + dt.timedelta(days=1)


def _render_heatmap(calendar: dict, *, chart_key: str) -> None:
    """学习热力图；chart_key 必传——主视图与折叠区各渲染一次，需唯一元素 ID。"""
    z = calendar["z"]
    if calendar["max"] == 0:
        st.caption("还没有学习记录，录入或复习错题后这里会点亮。")
        return
    heatmap = go.Heatmap(
        z=z,
        x=calendar["x"],
        y=calendar["y"],
        customdata=calendar.get("dates"),
        colorscale=heatmap_colorscale(),
        showscale=False,
        xgap=4,
        ygap=4,
        zmin=0,
        hovertemplate="%{customdata}（周 %{y}）：<b>%{z}</b> 题<extra></extra>",
    )
    fig = go.Figure(data=heatmap)
    fig.update_layout(
        margin=dict(t=10, b=10, l=10, r=10),
        height=190,
        paper_bgcolor="rgba(0,0,0,0)",
        font=_plotly_font(),
    )
    fig.update_xaxes(tickangle=0, tickfont=dict(size=9), gridcolor=_plotly_grid())
    fig.update_yaxes(tickfont=dict(size=9), gridcolor=_plotly_grid())
    st.plotly_chart(fig, width="stretch", key=chart_key, config={"displayModeBar": False})


def _render_mastery_donut(mastery_map: dict[int, float]) -> None:
    """掌握度三档分布环形图（数据=每题掌握度映射，无记录的题不参与）。"""
    if not mastery_map:
        st.caption("复习几道题后，这里会出现掌握度分布。")
        return
    buckets = {"已掌握": 0, "不稳固": 0, "薄弱": 0}
    for m in mastery_map.values():
        if m >= SHAKY_THRESHOLD:
            buckets["已掌握"] += 1
        elif m >= WEAK_THRESHOLD:
            buckets["不稳固"] += 1
        else:
            buckets["薄弱"] += 1
    total = sum(buckets.values())
    if total == 0:
        st.caption("尚无复习数据。")
        return
    overall = round(sum(mastery_map.values()) / total * 100)
    colors = {"已掌握": "#059669", "不稳固": "#d97706", "薄弱": "#dc2626"}
    fig = go.Figure(
        go.Pie(
            labels=list(buckets),
            values=list(buckets.values()),
            hole=0.66,
            sort=False,
            marker=dict(colors=[colors[k] for k in buckets]),
            textinfo="none",
        )
    )
    fig.update_layout(
        annotations=[
            dict(
                text=f"<b>{overall}%</b><br><span style='font-size:11px'>整体掌握</span>",
                x=0.5,
                y=0.5,
                font=dict(size=22, color=_plotly_ink()),
                showarrow=False,
            )
        ],
        margin=dict(t=6, b=6, l=6, r=6),
        height=190,
        paper_bgcolor="rgba(0,0,0,0)",
        font=_plotly_font(),
        showlegend=True,
        legend=dict(orientation="v", y=0.5, x=1.02, font=dict(size=11)),
    )
    st.plotly_chart(fig, width="stretch", key="chart_mastery_donut", config={"displayModeBar": False})
    for label, count in buckets.items():
        st.markdown(
            f"<div style='display:flex;justify-content:space-between;font-size:0.85rem'>"
            f"<span style='color:{colors[label]}'>● {label}</span>"
            f"<span>{count}</span></div>",
            unsafe_allow_html=True,
        )


def _render_accuracy_week(trend: list[dict]) -> None:
    """近 7 日复习正确率：柱色按正确率分档（好绿/一般蓝/差橙）。"""
    recent = trend[-7:] if trend else []
    if not recent:
        st.caption("还没有复习记录；完成一轮复习后这里会出现正确率。")
        return

    def _bar_color(acc) -> str:
        if acc is None:
            return "#cbd5e1"
        if acc >= 80:
            return "#059669"
        if acc >= 60:
            return "#3b82f6"
        return "#e8590c"

    fig = go.Figure(
        go.Bar(
            x=[t["date"][-5:] for t in recent],
            y=[t["accuracy"] or 0 for t in recent],
            marker_color=[_bar_color(t.get("accuracy")) for t in recent],
            width=0.55,
        )
    )
    fig.update_layout(
        margin=dict(t=10, b=10, l=10, r=10),
        height=200,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=_plotly_font(),
        yaxis=dict(range=[0, 105], visible=False),
        xaxis=dict(showgrid=False),
        showlegend=False,
    )
    st.plotly_chart(fig, width="stretch", key="chart_accuracy_week", config={"displayModeBar": False})


def render_dashboard(user: dict) -> None:
    service = get_question_service()
    page_header(
        "学情看板",
        f"{dt.datetime.now():%m 月 %d 日} · 功能已经很完整，这一屏回答“今天该做什么”",
    )

    ok, stats = safe_call(service.dashboard_stats, user["id"], error_title="学情数据加载失败")
    if not ok:
        st.stop()
    ok, due_list = safe_call(service.due_questions, user["id"], error_title="复习队列加载失败")
    if not ok:
        st.stop()
    ok, mastery_map = safe_call(
        service.mastery_by_question, user["id"], error_title="掌握度数据加载失败"
    )
    mastery_map = mastery_map or {}
    ok, today_graded = safe_call(
        service.today_graded_count, user["id"], error_title="今日进度加载失败"
    )
    today_graded = today_graded if ok else 0

    daily_goal = get_settings().daily_goal
    goal_pct = min(today_graded / daily_goal * 100, 100)
    goal_met = today_graded >= daily_goal

    # ---- 逾期/今天到期拆分（到期池内的三色构成）----
    today_start, tomorrow_start = _today_bounds()
    overdue = today_due = 0
    for q in due_list:
        if q.due_at is None:
            continue
        d = _aware(q.due_at)
        if d < today_start:
            overdue += 1
        elif d < tomorrow_start:
            today_due += 1

    weak_tags = stats.get("weak_tags", [])

    # ---- 顶栏问候 ----
    st.markdown(
        f"""
        <div style="display:flex;align-items:baseline;justify-content:space-between;flex-wrap:wrap">
          <div><span style="font-size:1.35rem;font-weight:700;color:var(--navy)">{_greeting()}，{user['username']}</span>
          <span class="mm-muted" style="margin-left:0.8rem">{dt.datetime.now():%m 月 %d 日 星期}{'一二三四五六日'[dt.datetime.now().weekday()]}</span></div>
          <div>{provider_badges()}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    main_col, side_col = st.columns([2.4, 1], gap="large")

    # ---- Hero 行动卡 ----
    with main_col:
        seg_total = max(len(due_list), 1)
        w_over = overdue / seg_total * 100
        w_today = today_due / seg_total * 100
        w_later = max(100 - w_over - w_today, 0)
        st.markdown(
            f"""
            <div class="mm-hero">
              <div class="mm-hero__title">今日主线：清空 {len(due_list)} 道待复习题</div>
              <div class="mm-hero__sub">{"⚠️ 其中有 " + str(overdue) + " 道已逾期，建议优先处理。" if overdue else "队列健康，按顺序复习即可。"}</div>
              <div class="mm-kpi-row">
                <div><div class="mm-kpi__value">{len(due_list)}</div><div class="mm-kpi__label">待复习</div></div>
                <div><div class="mm-kpi__value" style="color:#ff8a4c">{overdue}</div><div class="mm-kpi__label">已逾期</div></div>
                <div><div class="mm-kpi__value">{len(weak_tags)}</div><div class="mm-kpi__label">薄弱知识点</div></div>
                <div><div class="mm-kpi__value" style="color:{'#34d399' if goal_met else '#ffffff'}">{today_graded}<span style="font-size:0.8rem;color:#9fb0c9">/{daily_goal}</span></div><div class="mm-kpi__label">今日目标{' ✅' if goal_met else ''}</div></div>
                <div><div class="mm-kpi__value">{stats.get("streak", 0)}</div><div class="mm-kpi__label">连续学习（天）</div></div>
              </div>
              <div style="display:flex;align-items:center;gap:0.8rem;margin:0.8rem 0">
                <div style="flex:1;background:#24395c;border-radius:6px;height:8px;overflow:hidden">
                  <div style="background:{'#059669' if goal_met else '#3b82f6'};height:8px;width:{goal_pct:.0f}%;border-radius:6px"></div>
                </div>
                <span style="font-size:0.78rem;color:#9fb0c9;white-space:nowrap">今日目标 {today_graded}/{daily_goal} 题{' ✅' if goal_met else ''}</span>
              </div>
              <div class="mm-segbar">
                <div class="mm-segbar__overdue" style="width:{w_over}%"></div>
                <div class="mm-segbar__today" style="width:{w_today}%"></div>
                <div class="mm-segbar__later" style="width:{w_later}%"></div>
              </div>
              <div class="mm-segbar__legend">
                <span><span class="mm-dot mm-segbar__overdue"></span>已逾期 {overdue} 题</span>
                <span><span class="mm-dot mm-segbar__today"></span>今天到期 {today_due} 题</span>
                <span><span class="mm-dot mm-segbar__later"></span>稍后巩固 {len(due_list) - overdue - today_due} 题</span>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.button("▶ 开始今日复习", type="primary", width="stretch", key="hero_start"):
            go_to("review", mode="due")

    # ---- 连续学习 + 热力图 ----
    with side_col:
        streak_top, streak_best = st.columns(2)
        with streak_top:
            st.markdown(
                f"""
                <div class="mm-streak__value">{stats.get("streak", 0)}</div>
                <div class="mm-streak__unit">天连续学习</div>
                """,
                unsafe_allow_html=True,
            )
        with side_col:
            _render_heatmap(stats.get("calendar", {}), chart_key="heatmap_main")
            st.caption("■ 少 → 多")

    # ---- KPI 卡行（紧凑保留，E2E 与信息锚点） ----
    k1, k2, k3, k4 = st.columns(4)
    with k1:
        stat_card(stats["total"], "累计错题", accent=True)
    with k2:
        stat_card(len(stats["tag_stats"]), "涉及知识点")
    with k3:
        stat_card(stats["reviewed"], "已复习错题")
    with k4:
        stat_card(stats["mastered"], "已掌握 🏆")

    # ---- 待复习队列表格 + 薄弱知识点 ----
    queue_col, weak_col = st.columns([2.4, 1], gap="large")
    with queue_col:
        st.subheader("待复习队列")
        plan = service.today_plan(user["id"], size=5)
        if not plan:
            st.info("🎉 今日复习任务已清空，错题本处于健康状态。")
        else:
            for item in plan:
                q = item.question
                m = mastery_map.get(q.id)
                if m is None:
                    pill = '<span class="mm-pill mm-pill--none">未复习</span>'
                else:
                    pct = round(m * 100)
                    if m < WEAK_THRESHOLD:
                        pill = f'<span class="mm-pill mm-pill--weak">薄弱 {pct}%</span>'
                    elif m < SHAKY_THRESHOLD:
                        pill = f'<span class="mm-pill mm-pill--shaky">不稳定 {pct}%</span>'
                    else:
                        pill = f'<span class="mm-pill mm-pill--good">良好 {pct}%</span>'
                cols = st.columns([5, 2, 3, 2, 1])
                with cols[0]:
                    st.markdown(
                        f"**{q.content_markdown[:38]}**",
                        unsafe_allow_html=True,
                    )
                with cols[1]:
                    st.markdown(pill, unsafe_allow_html=True)
                with cols[2]:
                    st.caption(item.reason)
                with cols[3]:
                    st.caption("今天" if q.due_at is None else f"{_aware(q.due_at):%m-%d}")
                with cols[4]:
                    if st.button("›", key=f"queue_go_{q.id}", help="去复习这道"):
                        go_to("review", mode="plan", question_id=q.id)
            if st.button(f"全部 {len(due_list)} 道 ›", key="queue_all"):
                go_to("review", mode="due")

    with weak_col:
        st.subheader("薄弱知识点")
        if weak_tags:
            for tag_stat in weak_tags[:6]:
                st.markdown(
                    mastery_bar_html(
                        f"{tag_stat.tag} {tag_stat.count} 题",
                        tag_stat.mastery * 100,
                        color=mastery_color(tag_stat.mastery),
                        right=f"{int(tag_stat.mastery * 100)}%",
                    ),
                    unsafe_allow_html=True,
                )
            if st.button("查看全部 ›", key="weak_all", width="stretch"):
                go_to("notebook", tag=weak_tags[0].tag)
        else:
            st.caption("复习几道题后，这里会生成薄弱点分析。")

    st.markdown("<br>", unsafe_allow_html=True)

    # ---- 掌握度分布 + 近 7 日正确率 ----
    dist_col, acc_col = st.columns(2, gap="large")
    with dist_col:
        st.subheader("掌握度分布")
        _render_mastery_donut(mastery_map)
    with acc_col:
        st.subheader("近 7 日复习正确率")
        _render_accuracy_week(stats.get("accuracy_trend", []))

    # ---- 次要图表收进折叠 ----
    with st.expander("更多图表（录入趋势 / 学习日历 / 难度分布 / 掌握度趋势）"):
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
            font=_plotly_font(),
            xaxis=dict(type="category", showgrid=False),
            yaxis=dict(dtick=1, range=[0, max(3, max((a["count"] for a in activity), default=0) + 1)], gridcolor=_plotly_grid()),
        )
        st.plotly_chart(bar, width="stretch", key="chart_activity", config={"displayModeBar": False})

        cal_col, trend_col = st.columns(2)
        with cal_col:
            st.markdown("**学习日历**")
            _render_heatmap(stats["calendar"], chart_key="heatmap_extra")
        with trend_col:
            st.markdown("**掌握度趋势**")
            m_trend = stats.get("mastery_trend", [])
            if not m_trend or all(p["mastery"] == 0 for p in m_trend):
                st.caption("复习几道题后，这里会出现掌握度成长曲线。")
            else:
                line = px.line(
                    x=[p["date"] for p in m_trend],
                    y=[p["mastery"] for p in m_trend],
                    markers=True,
                    labels={"x": "日期", "y": "掌握度%"},
                )
                line.update_traces(line_color="#059669")
                line.update_layout(
                    margin=dict(t=10, b=10, l=10, r=10),
                    height=220,
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                    font=_plotly_font(),
                    yaxis=dict(range=[0, 105], gridcolor=_plotly_grid()),
                    xaxis=dict(showgrid=False),
                )
                st.plotly_chart(line, width="stretch", key="chart_mastery_trend", config={"displayModeBar": False})

        st.markdown("**难度分布**")
        _render_difficulty(stats.get("difficulty", {}))
