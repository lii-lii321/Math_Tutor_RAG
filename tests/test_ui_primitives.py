"""前端原语单测：badge / empty_state / mastery_color / safe_call（批A 回归保护）。"""
from __future__ import annotations

import pytest
import streamlit as st

from backend.services.mastery import SHAKY_THRESHOLD, WEAK_THRESHOLD
from frontend.common import badge, empty_state, mastery_color


def test_badge_default_tone():
    assert badge("x") == "<span class='mm-badge'>x</span>"


@pytest.mark.parametrize(
    ("tone", "cls"),
    [
        ("blue", "mm-badge mm-badge--blue"),
        ("warn", "mm-badge mm-badge--warn"),
        ("bad", "mm-badge mm-badge--bad"),
        ("ok", "mm-badge mm-badge--ok"),
    ],
)
def test_badge_tones(tone, cls):
    assert badge("t", tone) == f"<span class='{cls}'>t</span>"


def test_empty_state_renders_icon_and_title(monkeypatch):
    rendered = []
    monkeypatch.setattr(st, "markdown", lambda text, **kw: rendered.append(text))
    clicked = empty_state("🗂️", "没有错题", action_label=None)
    assert clicked is False
    assert any("mm-empty" in t and "没有错题" in t for t in rendered)


def test_mastery_color_thresholds_align_with_engine():
    """颜色分档必须与后端引擎阈值同源（<WEAK 红 / <SHAKY 琥珀 / 其余绿）。"""
    assert mastery_color(0.0) == "var(--weak)"
    assert mastery_color(WEAK_THRESHOLD - 0.01) == "var(--weak)"
    assert mastery_color(WEAK_THRESHOLD + 0.01) == "var(--shaky)"
    assert mastery_color(SHAKY_THRESHOLD - 0.01) == "var(--shaky)"
    assert mastery_color(SHAKY_THRESHOLD + 0.01) == "var(--good)"
    assert mastery_color(1.0) == "var(--good)"


class TestSafeCall:
    def test_ok_path_returns_result(self):
        from frontend.components import safe_call

        ok, result = safe_call(lambda a, b: a + b, 1, b=2)
        assert ok is True and result == 3

    def test_error_path_renders_error_card(self, monkeypatch):
        from frontend.components import safe_call

        rendered = []

        class _NullCtx:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        def _fake_markdown(text, **kw):
            rendered.append(text)

        monkeypatch.setattr(st, "error", _fake_markdown)
        monkeypatch.setattr(st, "expander", lambda *a, **kw: _NullCtx())
        monkeypatch.setattr(st, "code", lambda text: rendered.append(text))

        def _boom():
            raise RuntimeError("内部主机名 secret-db")

        ok, result = safe_call(_boom, error_title="加载失败")
        assert ok is False and result is None
        assert any("加载失败" in t for t in rendered), "必须有用户可读降级文案"

    def test_error_path_renders_detail_in_expander(self, monkeypatch):
        from frontend.components import safe_call

        code_blocks = []

        class _NullCtx:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        monkeypatch.setattr(st, "error", lambda text, **kw: None)
        monkeypatch.setattr(st, "expander", lambda *a, **kw: _NullCtx())
        monkeypatch.setattr(st, "code", lambda text, **kw: code_blocks.append(text))

        def _boom():
            raise RuntimeError("内部细节 secret-db-host")

        safe_call(_boom, error_title="加载失败")
        assert any("secret-db-host" in b for b in code_blocks), "细节应折叠进技术详情"


class _NullCtx:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False
