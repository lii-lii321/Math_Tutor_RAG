"""设置页：账号信息、AI 运行状态、改密、数据说明。"""
from __future__ import annotations

import streamlit as st

from backend.config import get_settings
from backend.database import get_session
from backend.services.ai import get_provider_status
from backend.services.auth import AuthService
from frontend.common import get_question_service, initials, page_header


def render_settings_page(user: dict) -> None:
    settings = get_settings()
    service = get_question_service()
    page_header("设置", "账号与系统状态")

    col_account, col_system = st.columns([2, 3])

    with col_account:
        with st.container(border=True):
            st.markdown("#### 账号")
            st.markdown(
                f"""
                <div style="display:flex;align-items:center;gap:0.9rem;margin-bottom:0.8rem">
                  <div class="user-avatar">{initials(user['username'])}</div>
                  <div>
                    <div style="font-weight:600">{user['username']}</div>
                    <div class="mm-muted">角色：{user['role']}</div>
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            with st.form("change_password_form"):
                old_pwd = st.text_input("原密码", type="password")
                new_pwd = st.text_input("新密码（至少 6 位）", type="password")
                if st.form_submit_button("修改密码"):
                    with get_session() as session:
                        result = AuthService(session).change_password(
                            user["id"], old_pwd, new_pwd
                        )
                    if result.ok:
                        st.success(result.message)
                    else:
                        st.error(result.message)

    with col_system:
        with st.container(border=True):
            st.markdown("#### AI 引擎")
            info = get_provider_status()
            if info.demo_mode:
                st.markdown(
                    '<span class="mm-badge mm-badge--warn">演示模式</span>',
                    unsafe_allow_html=True,
                )
                st.caption(
                    "未检测到 API Key。复制 `.env.example` 为 `.env` 并填入任一 "
                    "OpenAI 兼容服务（SiliconFlow / 通义 / GLM / DeepSeek / Ollama）或 Gemini 的 Key，"
                    "重启后自动启用真实模型。"
                )
            else:
                st.markdown(
                    f'<span class="mm-badge mm-badge--ok">{info.provider}</span> '
                    f'<span class="mm-badge">模型：{info.model}</span>',
                    unsafe_allow_html=True,
                )

            st.markdown("#### RAG 向量库")
            rag_available = service.vector_store.is_available()
            if rag_available:
                st.markdown(
                    '<span class="mm-badge mm-badge--ok">ChromaDB 运行中</span>',
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    '<span class="mm-badge mm-badge--warn">不可用（已降级为关键词检索）</span>',
                    unsafe_allow_html=True,
                )

            st.markdown("#### 存储")
            st.markdown(
                f"<span class='mm-muted'>数据库：{settings.database_url.split('://')[0]}</span>　"
                f"<span class='mm-muted'>向量库：{settings.chroma_dir.name}</span>",
                unsafe_allow_html=True,
            )
            st.caption("默认 SQLite 零配置；配置 DATABASE_URL 可切换 MySQL / PostgreSQL。")
