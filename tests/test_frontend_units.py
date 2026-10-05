"""前端层最小单测（提升路线 #1 的遗留半截）：纯函数助手 + 注册表不变量。

只测不依赖 Streamlit 运行时的纯逻辑（HTML 构造器、主题 token、导航注册表、
i18n 回退、safe_call 包装）；页面级冒烟由 tests/test_app_smoke.py（AppTest）
与 Playwright E2E 分层覆盖。
"""
from __future__ import annotations

import pytest

from frontend import charts
from frontend.components import mastery_bar_html, mastery_fill_html, safe_call
from frontend.i18n import t
from frontend.nav import GROUP_LABELS, PAGE_KEYS, PAGES, resolve_label

# ---------- 导航注册表不变量 ----------

def test_nav_pages_have_unique_keys():
    keys = [page.key for page in PAGES]
    assert len(keys) == len(set(keys))


def test_nav_pages_have_nonempty_labels_and_valid_groups():
    for page in PAGES:
        assert page.label, f"{page.key} 标签为空"
        assert page.group in GROUP_LABELS, f"{page.key} 组 {page.group} 未注册"


def test_nav_page_keys_matches_registry():
    assert PAGE_KEYS == frozenset(page.key for page in PAGES)


def test_nav_only_students_is_teacher_only():
    teacher_pages = [page.key for page in PAGES if page.teacher_only]
    assert teacher_pages == ["students"]


def test_resolve_label_known_and_unknown():
    assert resolve_label("dashboard") == PAGES[0].label
    with pytest.raises(KeyError):
        resolve_label("no-such-page")


# ---------- i18n 回退 ----------

def test_i18n_returns_value_for_known_key():
    assert t("nav.dashboard") == "学情看板"


def test_i18n_falls_back_to_key_when_missing():
    assert t("no.such.key") == "no.such.key"


def test_i18n_unknown_lang_falls_back_to_zh():
    assert t("nav.dashboard", lang="xx") == "学情看板"


# ---------- charts 主题 token ----------

@pytest.fixture
def dark_mode():
    """bare 模式下 st.session_state 可用；测试后清理避免串扰。"""
    import streamlit as st

    st.session_state["dark_mode"] = True
    yield True
    st.session_state.pop("dark_mode", None)


@pytest.fixture
def light_mode():
    import streamlit as st

    st.session_state.pop("dark_mode", None)
    yield False


def test_charts_dark_tokens(dark_mode):
    assert charts.is_dark() is True
    assert charts.plotly_font()["color"] == "#e2e8f0"
    assert charts.plotly_grid() == "#334155"
    assert charts.plotly_ink() == "#f1f5f9"
    assert charts.heatmap_colorscale()[0][1] == "#1e293b"


def test_charts_light_tokens(light_mode):
    assert charts.is_dark() is False
    assert charts.plotly_font()["color"] == "#334155"
    assert charts.plotly_grid() == "#e2e8f0"
    assert charts.plotly_ink() == "#1a365d"
    assert charts.heatmap_colorscale()[0][1] == "#eef2ee"


def test_charts_plotly_layout_applies_theme(light_mode):
    import plotly.graph_objects as go

    fig = go.Figure(go.Bar(x=[1], y=[1]))
    charts.plotly_layout(fig, height=123)
    assert fig.layout.height == 123
    assert fig.layout.paper_bgcolor == "rgba(0,0,0,0)"


# ---------- 掌握度 HTML 构造器 ----------

def test_mastery_fill_html_contains_pct_and_color():
    html = mastery_fill_html(66.4, color="#2563eb")
    assert "66%" in html
    assert "#2563eb" in html


def test_mastery_bar_html_renders_label_and_right():
    html = mastery_bar_html("函数", 40.0, color="#dc2626", right="40%")
    assert "函数" in html
    assert "40%" in html
    assert "#dc2626" in html


def test_mastery_bar_html_right_only_when_given():
    """right 文本仅在显式传入时渲染；进度条宽度百分比始终存在。"""
    with_right = mastery_bar_html("函数", 40.0, color="#dc2626", right="40%")
    without_right = mastery_bar_html("函数", 40.0, color="#dc2626")
    assert "width:40%" in with_right and "width:40%" in without_right
    assert without_right.count("40%") < with_right.count("40%")


# ---------- safe_call 包装 ----------

def test_safe_call_returns_ok_with_result():
    ok, result = safe_call(lambda a, b: a + b, 2, 3)
    assert ok is True
    assert result == 5


def test_safe_call_degrades_on_exception():
    def _boom():
        raise RuntimeError("db down")

    ok, result = safe_call(_boom, error_title="加载失败")
    assert ok is False
    assert result is None
