"""错题本筛选的 URL 参数 schema 与纯函数编解码（不 import streamlit，便于单测）。

URL 参数只承载错题本页的筛选 / 视图 / 页码状态，统一 ``nb_`` 前缀：

- ``encode``：默认值不写 URL，分享链接保持最短；
- ``decode``：非法值一律回退默认，不抛异常（URL 属外部输入，不可信）。

``st.query_params`` 的读写薄适配层在 ``frontend/pages/notebook.py``（种子 /
写回 / 清除）与 ``app.py``（离开错题本的迁移门控清理）。
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

# ---------- 枚举选项（notebook.py 控件与其共用，保持单一来源） ----------
VIEW_OPTIONS: tuple[str, ...] = ("📋", "🔲")
SORT_OPTIONS: tuple[str, ...] = (
    "最新录入",
    "最早录入",
    "复习次数最少",
    "最近复习",
    "掌握度最低",
)
TAG_DEFAULT = "全部"
STUDENT_DEFAULT = "全部学生"
PAGE_DEFAULT = 0
KEYWORD_DEFAULT = ""

_TRUE_TEXT = frozenset({"1", "true"})
_FALSE_TEXT = frozenset({"0", "false"})

# nb_* 参数 -> notebook 控件 key（app.py 离开清理与 notebook 种子共用）
_PARAM_WIDGET_KEYS: dict[str, str] = {
    "nb_kw": "notebook_search",
    "nb_tag": "notebook_tag",
    "nb_sort": "notebook_sort",
    "nb_view": "notebook_view",
    "nb_sem": "notebook_sem",
    "nb_due": "notebook_due",
    "nb_mastered": "notebook_mastered",
    "nb_weak": "notebook_weak",
    "nb_starred": "notebook_starred",
    "nb_student": "notebook_student",
    "nb_page": "notebook_page",
}
PARAM_NAMES: tuple[str, ...] = tuple(_PARAM_WIDGET_KEYS)
WIDGET_KEYS: tuple[str, ...] = tuple(dict.fromkeys(_PARAM_WIDGET_KEYS.values()))

# 规范化筛选字典的默认值（decode 回退 / encode 省略的基准）
_FILTER_DEFAULTS: dict[str, Any] = {
    "keyword": KEYWORD_DEFAULT,
    "tag": TAG_DEFAULT,
    "sort": SORT_OPTIONS[0],
    "view": VIEW_OPTIONS[0],
    "semantic": True,
    "only_due": False,
    "only_mastered": False,
    "only_weak": False,
    "only_starred": False,
    "student": STUDENT_DEFAULT,
    "page": PAGE_DEFAULT,
}


def _as_scalar(value: Any) -> Any:
    """parse_qs 风格的列表值取最后一个（与 st.query_params 单值语义一致）。"""
    if isinstance(value, (list, tuple)):
        return value[-1] if value else None
    return value


def _decode_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    text = str(value).strip().lower()
    if text in _TRUE_TEXT:
        return True
    if text in _FALSE_TEXT:
        return False
    return default


def decode_filters(params: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """URL 参数 -> 规范化筛选字典；键与 :data:`_FILTER_DEFAULTS` 一一对应。

    tag / student 的取值合法性依赖当前用户的实时选项，由 notebook.py
    在种入控件前再校验；这里只做类型与枚举层面的兜底。
    """
    raw = {
        name: _as_scalar((params or {}).get(name)) for name in _PARAM_WIDGET_KEYS
    }
    try:
        page = int(str(raw["nb_page"]))
    except (TypeError, ValueError):
        page = PAGE_DEFAULT
    if page < 0:
        page = PAGE_DEFAULT
    return {
        "keyword": KEYWORD_DEFAULT if raw["nb_kw"] is None else str(raw["nb_kw"]),
        "tag": TAG_DEFAULT if raw["nb_tag"] is None else str(raw["nb_tag"]),
        "sort": raw["nb_sort"] if raw["nb_sort"] in SORT_OPTIONS else SORT_OPTIONS[0],
        "view": raw["nb_view"] if raw["nb_view"] in VIEW_OPTIONS else VIEW_OPTIONS[0],
        "semantic": _decode_bool(raw["nb_sem"], True),
        "only_due": _decode_bool(raw["nb_due"], False),
        "only_mastered": _decode_bool(raw["nb_mastered"], False),
        "only_weak": _decode_bool(raw["nb_weak"], False),
        "only_starred": _decode_bool(raw["nb_starred"], False),
        "student": STUDENT_DEFAULT if raw["nb_student"] is None else str(raw["nb_student"]),
        "page": page,
    }


def encode_filters(filters: Mapping[str, Any] | None = None) -> dict[str, str]:
    """规范化筛选字典 -> URL 参数；默认值不写 URL。缺省键按默认值处理。"""
    merged: dict[str, Any] = {**_FILTER_DEFAULTS, **dict(filters or {})}
    encoded: dict[str, str] = {}
    if merged["keyword"]:
        encoded["nb_kw"] = str(merged["keyword"])
    if merged["tag"] and merged["tag"] != TAG_DEFAULT:
        encoded["nb_tag"] = str(merged["tag"])
    if merged["sort"] != SORT_OPTIONS[0]:
        encoded["nb_sort"] = str(merged["sort"])
    if merged["view"] != VIEW_OPTIONS[0]:
        encoded["nb_view"] = str(merged["view"])
    if merged["semantic"] is False:
        encoded["nb_sem"] = "0"
    if merged["only_due"]:
        encoded["nb_due"] = "1"
    if merged["only_mastered"]:
        encoded["nb_mastered"] = "1"
    if merged["only_weak"]:
        encoded["nb_weak"] = "1"
    if merged["only_starred"]:
        encoded["nb_starred"] = "1"
    if merged["student"] and merged["student"] != STUDENT_DEFAULT:
        encoded["nb_student"] = str(merged["student"])
    try:
        page = int(merged["page"])
    except (TypeError, ValueError):
        page = PAGE_DEFAULT
    if page > 0:
        encoded["nb_page"] = str(page)
    return encoded
