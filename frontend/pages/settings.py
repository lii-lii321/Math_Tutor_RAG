"""设置页：账号信息、AI 运行状态、改密、数据备份。"""
from __future__ import annotations

import datetime
import json

import streamlit as st

from backend.config import get_settings
from backend.database import get_session
from backend.services.ai import get_provider_status
from backend.services.auth import AuthService
from backend.services.full_backup import export_full_backup, import_full_backup
from backend.services.milestone import get_daily_goal, set_daily_goal
from frontend.common import get_question_service, initials, page_header
from frontend.components import safe_call


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
            st.markdown("#### 每日目标")
            with st.form("daily_goal_form"):
                goal_input = st.number_input(
                    "每日复习目标（题/天）",
                    min_value=1,
                    max_value=200,
                    value=get_daily_goal(user["id"]),
                    help="看板 Hero 的今日目标进度按此计算；1-200 与全局默认值域同源",
                )
                if st.form_submit_button("保存目标"):
                    try:
                        set_daily_goal(user["id"], int(goal_input))
                        st.toast(f"每日目标已设为 {int(goal_input)} 题", icon="🎯")
                    except ValueError as exc:
                        st.error(str(exc))
            st.caption("未单独设置时回退全局默认。")
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

            st.markdown("#### AI 调用遥测（最近 200 次）")
            from backend.services.ai import telemetry

            summary = telemetry.summarize()
            if summary["calls"] == 0:
                st.caption("暂无 AI 调用记录。")
            else:
                st.markdown(
                    f"""<div class="mm-muted">
                    调用 <b>{summary['calls']}</b> 次 ·
                    成功率 <b>{summary['success_rate']}%</b> ·
                    平均延迟 <b>{summary['avg_latency_ms']} ms</b>
                    </div>""",
                    unsafe_allow_html=True,
                )
                for op, bucket in summary["by_operation"].items():
                    st.caption(f"- {op}：{bucket['count']} 次，平均 {bucket['avg_ms']} ms")

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

            st.markdown("#### 关于")
            st.markdown(
                f"<span class='mm-muted'>📘 MathMaster Edu v{settings.app_version}</span>",
                unsafe_allow_html=True,
            )
            st.caption(
                "视觉大模型 × RAG 智能错题本 · SM-2 间隔重复 · 掌握度画像 · AI Tutor。"
                "部署与配置见 docs/DEPLOYMENT.md。"
            )

    with st.container(border=True):
        st.markdown("#### 标签管理")
        ok, usage = safe_call(service.tag_usage, user["id"], error_title="标签加载失败")
        if not ok:
            usage = {}
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
        st.markdown("#### 数据体检")
        st.caption("核对向量索引与数据库的一致性、扫描孤儿图片；发现问题可一键修复。")
        from backend.services.data_health import DataHealthService

        health_service = DataHealthService()
        if st.button("🩺 开始体检", width="stretch"):
            with st.spinner("体检中…"):
                st.session_state["health_report"] = health_service.check(user["id"])
            st.toast("体检完成", icon="🩺")

        report = st.session_state.get("health_report")
        if report:
            ok = report["issues"] == 0
            badge = (
                '<span class="mm-badge mm-badge--ok">全部健康</span>'
                if ok
                else f'<span class="mm-badge mm-badge--warn">发现 {report["issues"]} 处问题</span>'
            )
            st.markdown(
                f"""<div class="mm-muted" style="margin:0.4rem 0">
                错题 <b>{report['question_count']}</b> 道　{badge}<br>
                向量库：{'可用' if report['vector_available'] else '不可用（降级关键词检索）'}<br>
                缺失索引 <b>{report['missing_index']}</b>　残留索引 <b>{report['stale_index']}</b>　孤儿图片 <b>{report['orphan_image_count']}</b> 张（{report['orphan_image_mb']} MB）
                </div>""",
                unsafe_allow_html=True,
            )
            if report["missing_index"] or report["stale_index"]:
                if st.button("🔧 修复向量索引（重建缺失 + 清理残留）", width="stretch"):
                    with st.spinner("重建索引中…"):
                        result = health_service.repair_index(user["id"])
                    st.toast(f"已重建 {result['reindexed']} 题、清理 {result['removed']} 条残留", icon="🔧")
                    st.session_state["health_report"] = health_service.check(user["id"])
                    st.rerun()
            if report["orphan_image_count"]:
                if st.button(
                    f"🧹 清理 {report['orphan_image_count']} 张孤儿图片（{report['orphan_image_mb']} MB）",
                    width="stretch",
                ):
                    removed = health_service.cleanup_orphan_images(user["id"])
                    st.toast(f"已清理 {removed} 张", icon="🧹")
                    st.session_state["health_report"] = health_service.check(user["id"])
                    st.rerun()

    with st.container(border=True):
        st.markdown("#### 数据备份")
        st.caption(
            "JSON 备份仅含题面文字（解析、标签、考点），不含原图与复习进度；"
            "完整备份 zip 另含原图与复习进度（SM-2 调度、星标、笔记、复习日志）。"
        )
        # 惰性生成：点「生成备份」才做全量导出，不再每次渲染都全表扫描
        if st.button("📦 生成备份内容", width="stretch", key="backup_generate"):
            with st.spinner("生成备份中…"):
                st.session_state["backup_data"] = service.export_user_data(user["id"])
                st.session_state["backup_csv"] = service.export_user_csv(user["id"])
            st.toast("备份内容已生成", icon="📦")
        backup_data = st.session_state.get("backup_data")
        col_dl, col_up = st.columns(2)
        with col_dl:
            download_disabled = backup_data is None
            st.download_button(
                "导出备份 (JSON)",
                data=json.dumps(backup_data, ensure_ascii=False, indent=2) if backup_data else "",
                file_name=f"mathmaster_backup_{datetime.date.today():%Y%m%d}.json",
                mime="application/json",
                width="stretch",
                disabled=download_disabled,
            )
            csv_data = st.session_state.get("backup_csv")
            st.download_button(
                "导出 CSV（Excel）",
                data=csv_data or "",
                file_name=f"mathmaster_{datetime.date.today():%Y%m%d}.csv",
                mime="text/csv",
                width="stretch",
                disabled=not csv_data,
            )
            # 完整备份 zip：惰性生成沿用上方模式
            if st.button(
                "🗜️ 生成完整备份（zip：题目+原图+复习进度）",
                width="stretch",
                key="full_backup_generate",
            ):
                with st.spinner("生成完整备份中…"):
                    st.session_state["full_backup_bytes"] = export_full_backup(
                        user["id"]
                    ).getvalue()
                st.toast("完整备份已生成", icon="🗜️")
            full_backup_bytes = st.session_state.get("full_backup_bytes")
            st.download_button(
                "导出完整备份 (ZIP)",
                data=full_backup_bytes or b"",
                file_name=f"mathmaster_full_{datetime.date.today():%Y%m%d}.zip",
                mime="application/zip",
                width="stretch",
                disabled=not full_backup_bytes,
            )
        with col_up:
            upload = st.file_uploader(
                "导入备份（JSON 或完整备份 ZIP）", type=["json", "zip"], key="backup_import"
            )
            if upload is not None and st.button("开始导入", width="stretch"):
                try:
                    if (upload.name or "").lower().endswith(".zip"):
                        result = import_full_backup(user["id"], upload.getvalue())
                        extra = (
                            f" · 跳过无效 {result['skipped']}" if result["skipped"] else ""
                        )
                        st.success(
                            f"完整备份导入完成：题目 {result['questions']} / "
                            f"日志 {result['logs']} / 图片 {result['images']}"
                            f"（缺失 {result['missing_images']}）{extra}"
                        )
                    else:
                        payload = json.loads(upload.getvalue().decode("utf-8"))
                        imported = service.import_user_data(user["id"], payload)
                        st.success(f"成功导入 {imported} 道错题")
                except Exception as exc:  # noqa: BLE001 - 导入失败给出明确原因
                    st.error(f"导入失败：{exc}")
