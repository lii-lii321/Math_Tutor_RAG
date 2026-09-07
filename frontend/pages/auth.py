"""登录 / 注册页。密码经 bcrypt 校验，注册入参经 Pydantic 校验。"""
from __future__ import annotations

import streamlit as st

from backend.database import get_session, init_db
from backend.models.schemas import RegisterInput
from backend.services.auth import AuthService
from frontend.common import login_user


def render_auth_page() -> None:
    init_db()
    st.markdown(
        """
        <div class="mm-login">
            <h1 class="mm-login__title">MathMaster Edu</h1>
            <p class="mm-login__subtitle">基于视觉大模型与 RAG 的智能错题本</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    tab_login, tab_register = st.tabs(["登录", "注册"])

    with tab_login:
        with st.form("login_form", clear_on_submit=False):
            username = st.text_input("用户名", placeholder="admin / demo")
            password = st.text_input("密码", type="password")
            if st.form_submit_button("登录", type="primary", use_container_width=True):
                if not username or not password:
                    st.warning("请输入用户名和密码")
                else:
                    with get_session() as session:
                        result = AuthService(session).login(username, password)
                    if result.ok:
                        login_user(result.user_id, result.username, result.role)
                        st.rerun()
                    else:
                        st.error(result.message)
        st.caption("首次运行自动创建种子账号：admin / admin123（教师）　demo / demo123（学生）")

    with tab_register:
        with st.form("register_form"):
            new_username = st.text_input("用户名（2-32 字符）")
            new_password = st.text_input("密码（至少 6 位）", type="password")
            new_password2 = st.text_input("确认密码", type="password")
            role = st.selectbox("角色", ["student", "teacher"], format_func=lambda v: "学生" if v == "student" else "教师")
            if st.form_submit_button("创建账号", use_container_width=True):
                if new_password != new_password2:
                    st.error("两次输入的密码不一致")
                else:
                    try:
                        payload = RegisterInput(
                            username=new_username, password=new_password, role=role
                        )
                    except Exception as exc:  # noqa: BLE001 - 展示校验错误
                        st.error(f"输入不合法：{exc}")
                        st.stop()
                    with get_session() as session:
                        result = AuthService(session).register(payload)
                    if result.ok:
                        st.success("注册成功，请切换到「登录」")
                    else:
                        st.error(result.message)
