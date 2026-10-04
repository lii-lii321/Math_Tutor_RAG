"""Plotly 主题助手：深浅色统一适配的单点来源。

图表层只从这里取字体/网格/画布 token，深色模式由 session_state 的
dark_mode 开关驱动；各页面不再自绘配色（dashboard 的同名私有函数
是对本模块的别名转发，行为与 2.12 之前完全一致）。
"""
from __future__ import annotations

import streamlit as st


def is_dark() -> bool:
    return bool(st.session_state.get("dark_mode", False))


def plotly_font() -> dict:
    """图表字体：深色用亮墨，浅色用板岩灰。"""
    return dict(family="sans-serif", color="#e2e8f0" if is_dark() else "#334155")


def plotly_grid() -> str:
    """网格/轴线色：深色用石板线，浅色用雾灰。"""
    return "#334155" if is_dark() else "#e2e8f0"


def plotly_ink() -> str:
    """强对比文本（环形图中心标注等）：深色近白，浅色深藏青。"""
    return "#f1f5f9" if is_dark() else "#1a365d"


def plotly_layout(fig, height: int = 220) -> None:
    """统一 Plotly 主题：透明底 + 主题字体 + 主题网格。"""
    grid = plotly_grid()
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=plotly_font(),
        height=height,
    )
    fig.update_xaxes(gridcolor=grid, linecolor=grid)
    fig.update_yaxes(gridcolor=grid)


def heatmap_colorscale() -> list[list[str | float]]:
    """学习热力图色带：零值格深色模式下用卡片色，避免整版刺眼亮块。"""
    if is_dark():
        return [[0, "#1e293b"], [0.4, "#2f6b52"], [0.75, "#3f9e74"], [1, "#34d399"]]
    return [[0, "#eef2ee"], [0.4, "#a7d7b8"], [0.75, "#4caf83"], [1, "#059669"]]
