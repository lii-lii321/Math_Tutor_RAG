"""视图层通用工具：样式加载、会话状态、公共小组件。"""
from __future__ import annotations

import pathlib

import streamlit as st

from backend.services.ai import get_provider_status
from backend.services.question_service import QuestionService

_ASSETS = pathlib.Path(__file__).parent / "assets" / "style.css"


def load_css() -> None:
    if _ASSETS.exists():
        st.markdown(f"<style>{_ASSETS.read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)


def current_user() -> dict | None:
    return st.session_state.get("user")


def login_user(user_id: int, username: str, role: str) -> None:
    st.session_state["user"] = {"id": user_id, "username": username, "role": role}


def logout_user() -> None:
    st.session_state["user"] = None


@st.cache_resource
def get_question_service() -> QuestionService:
    """进程级共享：AI 客户端与向量库句柄复用，避免每页重建。

    QuestionService 内部每次操作独立开短事务，缓存实例是安全的。
    """
    return QuestionService()


def stat_card(value, label: str, accent: bool = False) -> None:
    st.markdown(
        f"""
        <div class="mm-stat{' mm-stat--accent' if accent else ''}">
            <div class="mm-stat__value">{value}</div>
            <div class="mm-stat__label">{label}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def provider_badges() -> str:
    info = get_provider_status()
    if info.demo_mode:
        mode = '<span class="mm-badge mm-badge--warn">演示模式 · 未配置 API Key</span>'
    else:
        mode = f'<span class="mm-badge mm-badge--ok">AI: {info.model}</span>'
    return mode


def page_header(title: str, subtitle: str = "") -> None:
    st.markdown(
        f"<h2 style='margin-bottom:0.1rem'>{title}</h2>"
        + (f"<p class='mm-muted'>{subtitle}</p>" if subtitle else ""),
        unsafe_allow_html=True,
    )


def initials(name: str) -> str:
    return (name[:2] or "U").upper()


_LABEL_TO_KEY = {
    "学情看板": "dashboard",
    "AI 录题": "tutor",
    "错题本": "notebook",
    "今日复习": "review",
    "知识图谱": "graph",
    "设置": "settings",
}


def go_to(page_key: str, **params) -> None:
    """跨页跳转：记录目标导航项，触发重跑。

    注意：菜单组件的 session key 只能在其「本次实例化之前」修改，
    因此这里仅写入 _pending_nav，由 app.py 在渲染侧边栏前消费。
    """
    label = next(label for label, key in _LABEL_TO_KEY.items() if key == page_key)
    st.session_state["_pending_nav"] = label
    for name, value in params.items():
        st.session_state[f"param_{name}"] = value
    st.rerun()


def pop_params(*names: str) -> dict:
    """读取并清除 go_to 传递的页面参数（一次性）。"""
    return {
        name: st.session_state.pop(f"param_{name}", None)
        for name in names
        if f"param_{name}" in st.session_state
    }
