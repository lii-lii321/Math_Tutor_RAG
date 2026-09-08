"""MathMaster Edu — 应用入口。

Streamlit 运行：streamlit run app.py
"""
from __future__ import annotations

import streamlit as st
import streamlit_antd_components as sac

from backend.config import get_settings
from frontend.common import current_user, load_css, logout_user
from frontend.pages.auth import render_auth_page
from frontend.pages.dashboard import render_dashboard
from frontend.pages.notebook import render_notebook_page
from frontend.pages.review import render_review_page
from frontend.pages.settings import render_settings_page
from frontend.pages.tutor import render_tutor_page

settings = get_settings()

st.set_page_config(
    page_title=f"{settings.app_name} · 智能错题本",
    page_icon="📘",
    layout="wide",
    initial_sidebar_state="expanded",
)
load_css()


_PAGES = {
    "学情看板": "dashboard",
    "AI 录题": "tutor",
    "错题本": "notebook",
    "今日复习": "review",
    "知识图谱": "graph",
    "设置": "settings",
}


def _render_sidebar(user: dict) -> str:
    from frontend.common import initials

    with st.sidebar:
        st.markdown(
            """
            <div style="text-align:center;padding:1.2rem 0 0.6rem 0">
              <div style="font-size:1.15rem;font-weight:700;color:#1a365d">📘 MathMaster Edu</div>
              <div class="mm-muted">视觉大模型 × RAG 错题本</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        menu = sac.menu(
            [sac.MenuItem(label) for label in _PAGES],
            format_func="title",
            color="#2563eb",
            variant="light",
            open_all=True,
            key="nav",
        )
        st.markdown("<hr>", unsafe_allow_html=True)
        st.markdown(
            f"""
            <div style="display:flex;align-items:center;gap:0.6rem">
              <div class="user-avatar">{initials(user['username'])}</div>
              <div>
                <div style="font-weight:600;font-size:0.92rem">{user['username']}</div>
                <div class="mm-muted">{user['role']}</div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.button("退出登录", use_container_width=True):
            logout_user()
            st.rerun()
    return _PAGES.get(menu or "学情看板", "dashboard")


def main() -> None:
    user = current_user()
    if user is None:
        render_auth_page()
        return

    page = _render_sidebar(user)
    if page == "dashboard":
        render_dashboard(user)
    elif page == "tutor":
        render_tutor_page(user)
    elif page == "notebook":
        render_notebook_page(user)
    elif page == "review":
        render_review_page(user)
    elif page == "graph":
        from frontend.pages.graph import render_graph_page

        render_graph_page(user)
    elif page == "settings":
        render_settings_page(user)


if __name__ == "__main__":
    main()
