"""导航注册表一致性：frontend/nav.py 是页面 key 与标签的唯一来源。

回归背景：旧版 frontend/common.py 的 _LABEL_TO_KEY 缺 mastery/assistant/students，
go_to("mastery") 在无 default 的 next() 上抛 StopIteration。
"""
from __future__ import annotations

import pytest

from frontend import common, nav
from frontend.i18n import t


def test_every_registry_key_resolves():
    """nav.py 里每个 key 都能被 go_to 的解析函数解析（不抛 StopIteration）。"""
    for page in nav.PAGES:
        assert page.key in nav.PAGE_KEYS
        assert nav.resolve_label(page.key) == page.label


def test_previously_missing_keys_reachable():
    """mastery/assistant/students 可达（旧版 _LABEL_TO_KEY 对其抛 StopIteration）。"""
    for key in ("mastery", "assistant", "students"):
        assert nav.resolve_label(key) == t(f"nav.{key}")


def test_label_to_key_matches_registry():
    """common._LABEL_TO_KEY 的标签与 key 集合和 nav.py 完全一致。"""
    assert common._LABEL_TO_KEY == {page.label: page.key for page in nav.PAGES}
    assert set(common._LABEL_TO_KEY.values()) == set(nav.PAGE_KEYS)


def test_resolution_covers_app_sidebar_keys():
    """可解析的 key 集合与 app.py 侧边栏使用的 key 集合一致。"""
    import app

    app_keys = set(app._PAGES.values()) | set(app._TEACHER_PAGES.values())
    assert app_keys == set(nav.PAGE_KEYS)
    for page in nav.PAGES:
        table = app._TEACHER_PAGES if page.teacher_only else app._PAGES
        assert table[page.label] == page.key
        assert nav.resolve_label(page.key) == page.label


def test_unknown_key_raises_key_error():
    """未注册的 key 抛明确 KeyError，而非裸 next() 的 StopIteration。"""
    with pytest.raises(KeyError):
        nav.resolve_label("nonexistent")
