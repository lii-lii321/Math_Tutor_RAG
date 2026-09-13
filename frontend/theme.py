"""主题：深色模式（会话级切换，注入 CSS 覆盖）。"""
from __future__ import annotations

import streamlit as st

_DARK_CSS = """
<style>
/* MUJI 深色主题（会话级覆盖） */
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
.mm-mastery__track { background: #334155; }
div[data-testid="stExpander"] details > summary { color: #e2e8f0; }
.stTextInput input, textarea { background: #0f172a !important; color: #e2e8f0 !important; }
hr { border-top-color: #334155 !important; }
</style>
"""


def apply_theme() -> None:
    """按会话开关注入深色 CSS（app.py 在 load_css() 之后调用）。"""
    if st.session_state.get("dark_mode"):
        st.markdown(_DARK_CSS, unsafe_allow_html=True)
