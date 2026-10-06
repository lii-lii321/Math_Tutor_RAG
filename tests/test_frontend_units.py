"""前端层最小单测（提升路线 #1 的遗留半截）：纯函数助手 + 注册表不变量。

只测不依赖 Streamlit 运行时的纯逻辑（HTML 构造器、主题 token、导航注册表、
i18n 回退、safe_call 包装、query_state URL 编解码）；页面级冒烟由
tests/test_app_smoke.py（AppTest）与 Playwright E2E 分层覆盖。
"""
from __future__ import annotations

from pathlib import Path

import pytest

from frontend import charts
from frontend.components import mastery_bar_html, mastery_fill_html, safe_call
from frontend.i18n import t
from frontend.nav import GROUP_LABELS, PAGE_KEYS, PAGES, resolve_label
from frontend.query_state import (
    PARAM_NAMES,
    SORT_OPTIONS,
    VIEW_OPTIONS,
    WIDGET_KEYS,
    decode_filters,
    encode_filters,
)

_REPO_ROOT = Path(__file__).resolve().parent.parent

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


# ---------- query_state：URL 参数 schema 与编解码 ----------

def test_query_state_declares_eleven_nb_params():
    assert PARAM_NAMES == (
        "nb_kw",
        "nb_tag",
        "nb_sort",
        "nb_view",
        "nb_sem",
        "nb_due",
        "nb_mastered",
        "nb_weak",
        "nb_starred",
        "nb_student",
        "nb_page",
    )
    assert len(set(WIDGET_KEYS)) == len(PARAM_NAMES) == 11


def test_query_state_defaults_encode_to_empty_url():
    """默认值不写 URL：默认筛选的编码结果为空 dict。"""
    filters = decode_filters({})
    assert filters["keyword"] == ""
    assert filters["tag"] == "全部"
    assert filters["sort"] == SORT_OPTIONS[0]
    assert filters["view"] == VIEW_OPTIONS[0]
    assert filters["semantic"] is True
    assert filters["only_due"] is False
    assert filters["page"] == 0
    assert filters["student"] == "全部学生"
    assert encode_filters(filters) == {}


def test_query_state_encode_only_non_defaults():
    encoded = encode_filters(
        {
            "keyword": "二次函数",
            "semantic": False,
            "only_starred": True,
            "page": 2,
        }
    )
    assert encoded == {
        "nb_kw": "二次函数",
        "nb_sem": "0",
        "nb_starred": "1",
        "nb_page": "2",
    }


def test_query_state_decode_roundtrip_keeps_meaningful_params():
    params = {
        "nb_kw": "函数",
        "nb_sort": "掌握度最低",
        "nb_view": "🔲",
        "nb_due": "1",
        "nb_page": "3",
        "nb_student": "demo",
        "nb_sem": "0",
    }
    filters = decode_filters(params)
    assert filters["keyword"] == "函数"
    assert filters["sort"] == "掌握度最低"
    assert filters["view"] == "🔲"
    assert filters["only_due"] is True
    assert filters["semantic"] is False
    assert filters["page"] == 3
    assert filters["student"] == "demo"
    assert encode_filters(filters) == params


def test_query_state_decode_invalid_values_fall_back_to_defaults():
    """非法值回退：枚举外取默认、非法布尔回退、负页码归零。"""
    filters = decode_filters(
        {
            "nb_sort": "javascript:alert(1)",
            "nb_view": "card",
            "nb_sem": "yes",
            "nb_due": "2",
            "nb_page": "-3",
        }
    )
    assert filters["sort"] == SORT_OPTIONS[0]
    assert filters["view"] == VIEW_OPTIONS[0]
    assert filters["semantic"] is True
    assert filters["only_due"] is False
    assert filters["page"] == 0


def test_query_state_decode_handles_non_string_and_lists():
    """parse_qs 风格列表取最后一个；非字符串值强转 str；空列表回退。"""
    filters = decode_filters({"nb_kw": ["a", "b"], "nb_page": ["2"], "nb_tag": []})
    assert filters["keyword"] == "b"
    assert filters["page"] == 2
    assert filters["tag"] == "全部"
    assert decode_filters({"nb_kw": 42})["keyword"] == "42"
    assert decode_filters(None)["keyword"] == ""


# ---------- review.py fragment 化防回潮 ----------

def test_review_page_has_no_fragment_scoped_rerun():
    """整页上下文调用 st.rerun(scope="fragment") 必抛
    StreamlitInvalidLayoutContextError——review.py 必须保持零 scope=fragment。"""
    source = (_REPO_ROOT / "frontend" / "pages" / "review.py").read_text(
        encoding="utf-8"
    )
    assert 'scope="fragment"' not in source
    assert "scope='fragment'" not in source
    assert "@st.fragment" in source, "评分卡片区 fragment 化不应被移除"
