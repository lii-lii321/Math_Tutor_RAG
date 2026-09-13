"""设置页：账号信息、AI 运行状态、改密、数据备份。"""
from __future__ import annotations

import datetime
import json

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
            st.markdown("#### 外观")
            dark = st.toggle("深色模式", value=st.session_state.get("dark_mode", False))
            if dark != st.session_state.get("dark_mode"):
                st.session_state["dark_mode"] = dark
                st.rerun()
            st.caption("会话级设置，刷新后恢复默认浅色。")
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

            st.markdown("#### OCR（原图文字识别，可选）")
            if settings.ocr_enabled:
                try:
                    import rapidocr_onnxruntime  # noqa: F401

                    st.markdown(
                        '<span class="mm-badge mm-badge--ok">已启用</span>',
                        unsafe_allow_html=True,
                    )
                except ImportError:
                    st.markdown(
                        '<span class="mm-badge mm-badge--warn">已开启但缺少依赖：'
                        "pip install rapidocr-onnxruntime</span>",
                        unsafe_allow_html=True,
                    )
            else:
                st.markdown(
                    '<span class="mm-badge">未启用（.env 设 OCR_ENABLED=true 开启）</span>',
                    unsafe_allow_html=True,
                )

            st.markdown("#### 存储")
            st.markdown(
                f"<span class='mm-muted'>数据库：{settings.database_url.split('://')[0]}</span>　"
                f"<span class='mm-muted'>向量库：{settings.chroma_dir.name}</span>",
                unsafe_allow_html=True,
            )
            st.caption("默认 SQLite 零配置；配置 DATABASE_URL 可切换 MySQL / PostgreSQL。")

    with st.container(border=True):
        st.markdown("#### 标签管理")
        usage = service.tag_usage(user["id"])
        if not usage:
            st.caption("暂无标签。")
        else:
            st.caption("重命名或删除标签会同步更新所有错题与向量索引。")
            with st.form("tag_manage_form"):
                old_tag = st.selectbox("选择标签", list(usage.keys()))
                new_tag = st.text_input("重命名为（留空则不重命名）", placeholder="新标签名")
                col_r, col_d = st.columns(2)
                with col_r:
                    rename_clicked = st.form_submit_button("重命名", width="stretch")
                with col_d:
                    delete_clicked = st.form_submit_button("删除标签", width="stretch")
            if rename_clicked and new_tag.strip():
                try:
                    changed = service.rename_tag(user["id"], old_tag, new_tag.strip())
                    st.toast(f"已重命名 {changed} 题", icon="🏷️")
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))
            if delete_clicked:
                changed = service.delete_tag(user["id"], old_tag)
                st.toast(f"已从 {changed} 题移除标签", icon="🗑️")
                st.rerun()
            st.caption("当前使用情况：" + "、".join(f"{k}({v})" for k, v in usage.items()))

    with st.container(border=True):
        st.markdown("#### 数据备份")
        st.caption("导出全部错题为 JSON 备份文件；导入时按手动错题恢复，已含解析、标签与考点。")
        backup_data = service.export_user_data(user["id"])
        col_dl, col_up = st.columns(2)
        with col_dl:
            st.download_button(
                "导出备份 (JSON)",
                data=json.dumps(backup_data, ensure_ascii=False, indent=2),
                file_name=f"mathmaster_backup_{datetime.date.today():%Y%m%d}.json",
                mime="application/json",
                width="stretch",
            )
            csv_data = service.export_user_csv(user["id"])
            st.download_button(
                "导出 CSV（Excel）",
                data=csv_data,
                file_name=f"mathmaster_{datetime.date.today():%Y%m%d}.csv",
                mime="text/csv",
                width="stretch",
            )
        with col_up:
            upload = st.file_uploader("导入备份", type=["json"], key="backup_import")
            if upload is not None and st.button("开始导入", width="stretch"):
                try:
                    payload = json.loads(upload.getvalue().decode("utf-8"))
                    imported = service.import_user_data(user["id"], payload)
                    st.success(f"成功导入 {imported} 道错题")
                except Exception as exc:  # noqa: BLE001 - 导入失败给出明确原因
                    st.error(f"导入失败：{exc}")
