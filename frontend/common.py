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
