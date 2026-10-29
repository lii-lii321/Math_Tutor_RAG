"""主题：深色模式（会话级切换，只切 <html data-theme> 属性）。

样式真源是 frontend/assets/style.css：
- ``:root`` 浅色变量段 + ``[data-theme="dark"]`` 深色变量段；
- 本模块不再重定义任何变量、不再逐组件打补丁——页面里所有取
  ``var(--*)`` 的内联样式随属性自动翻面，Plotly 字面量配色由
  frontend/charts.semantic_colors() 与本开关同源（is_dark()）。

注入方式与 common.keyboard_shortcuts 相同（同源 iframe 组件向父文档
写属性，每帧重跑幂等：已处目标态则不重复写）。
"""
from __future__ import annotations

import streamlit as st
from streamlit.components.v1 import html as _components_html

_DARK_JS = (
    "<script>var d=window.parent.document.documentElement;"
    "if(d.getAttribute('data-theme')!=='dark')d.setAttribute('data-theme','dark');</script>"
)
_LIGHT_JS = (
    "<script>var d=window.parent.document.documentElement;"
    "if(d.getAttribute('data-theme'))d.removeAttribute('data-theme');</script>"
)


def apply_theme() -> None:
    """按会话开关注入 data-theme 切换脚本（app.py 在 load_css() 之后调用）。"""
    _components_html(
        _DARK_JS if st.session_state.get("dark_mode") else _LIGHT_JS,
        height=0,
    )
