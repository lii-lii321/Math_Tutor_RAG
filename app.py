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
    initial_sidebar_state="auto",  # 窄屏自动折叠，兼顾移动端
)
load_css()

from frontend.i18n import t  # noqa: E402
from frontend.theme import apply_theme  # noqa: E402  需在基础样式之后注入

apply_theme()

# PWA：manifest 与 Service Worker（静态目录 .streamlit/static/）
st.markdown(
    '<link rel="manifest" href="app/static/manifest.json">',
    unsafe_allow_html=True,
)
try:
    import streamlit.components.v1 as components

    components.html(
        """
<script>
if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('app/static/sw.js').catch(function () {});
}
</script>
""",
        height=0,
    )
except Exception:  # noqa: BLE001 - SW 注册失败不影响应用
    pass


_PAGES = {
    t("nav.dashboard"): "dashboard",
    t("nav.tutor"): "tutor",
    t("nav.notebook"): "notebook",
    t("nav.review"): "review",
    t("nav.graph"): "graph",
    t("nav.settings"): "settings",
}


_TEACHER_PAGES = {
    t("nav.students"): "students",
}


def _render_sidebar(user: dict) -> str:
    from frontend.common import initials

    visible = dict(_PAGES)
    if user.get("role") == "teacher":
        # 教师专属页插在「知识图谱」之前
        ordered = list(visible.items())
        insert_at = next(
            (i for i, (label, key) in enumerate(ordered) if key == "graph"),
            len(ordered),
        )
        ordered[insert_at:insert_at] = list(_TEACHER_PAGES.items())
        visible = dict(ordered)

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
        pending = st.session_state.pop("_pending_nav", None)  # 必须在菜单实例化前写入其 key
        if pending:
            st.session_state["nav"] = pending
        menu = sac.menu(
            [sac.MenuItem(label) for label in visible],
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
            <div class="mm-muted" style="text-align:center;margin-top:0.8rem;font-size:0.75rem">
              v{settings.app_version}
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.button("退出登录", width="stretch"):
            logout_user()
            st.rerun()
    all_pages = {**visible}
    return all_pages.get(menu or t("nav.dashboard"), "dashboard")


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
    elif page == "students":
        from frontend.pages.students import render_students_page

        render_students_page(user)
    elif page == "settings":
        render_settings_page(user)


if __name__ == "__main__":
    main()
