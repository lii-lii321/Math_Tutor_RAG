"""主题：深色模式（会话级切换，通过重定义 CSS 变量对实现，而非逐组件打补丁）。

新组件/新页面只引用 style.css 里的变量（--card/--ink/--line/--bg 等），
深色主题只需重定义变量即可整体适配，不再需要 20 条 !important 逐组件覆盖。
"""
from __future__ import annotations

import streamlit as st

_DARK_CSS = """
<style>
/* MUJI 深色主题：重定义变量对 + 少量结构性覆盖 */
:root, .stApp {
  --bg: #0f172a;
  --card: #1e293b;
  --navy: #f1f5f9;
  --slate: #e2e8f0;
  --slate-light: #94a3b8;
  --border: #334155;
  --muted: #94a3b8;
  --blue-soft: #172554;
}
.stApp { background: #0f172a; color: #e2e8f0; }
section[data-testid="stSidebar"] { background: #1e293b; border-right-color: #334155; }
h1, h2, h3, h4 { color: #f1f5f9 !important; }
.mm-card, .mm-stat, div[data-testid="stExpander"] {
  background: #1e293b !important; border-color: #334155 !important;
}
.mm-stat__value { color: #f1f5f9 !important; }
.mm-stat__label, .mm-muted { color: #94a3b8 !important; }
.mm-welcome { background: linear-gradient(135deg, #1e3a8a 0%, #172554 100%) !important; }
.mm-badge { background: #1e293b; color: #94a3b8; border-color: #334155; }
.mm-badge--blue { background: #172554; color: #93c5fd; border-color: #1e40af; }
.mm-badge--warn { background: #3b2f12; color: #fcd34d; border-color: #92400e; }
.mm-badge--bad  { background: #3f1d1d; color: #fca5a5; border-color: #991b1b; }
.mm-badge--ok   { background: #0f2e24; color: #6ee7b7; border-color: #065f46; }
.mm-mastery__track { background: #334155; }
.mm-mastery__row { color: #cbd5e1 !important; }
.mm-flashcard { background: #1e293b !important; border-color: #334155 !important; }
.mm-empty { color: #94a3b8 !important; }
div[data-testid="stExpander"] details > summary { color: #e2e8f0; }
.stTextInput input, textarea { background: #0f172a !important; color: #e2e8f0 !important; }
hr { border-top-color: #334155 !important; }
</style>
"""


def apply_theme() -> None:
    """按会话开关注入深色 CSS（app.py 在 load_css() 之后调用）。"""
    if st.session_state.get("dark_mode"):
        st.markdown(_DARK_CSS, unsafe_allow_html=True)
