"""AI 录题页：上传错题图片 → 结构化解析 → 自动入库与向量索引 → 举一反三。"""
from __future__ import annotations

import streamlit as st

from backend.services.question_service import sanitize_tags
from frontend.common import get_question_service, go_to, page_header


def render_tutor_page(user: dict) -> None:
    service = get_question_service()
    page_header("AI 录题", "上传错题照片，自动完成考点分析、详解与归档")

    info = service.ai.provider_info()
    if info.demo_mode:
        st.warning("当前为演示模式：未配置 AI_API_KEY，返回内置示例解析。在 .env 配置后即可调用真实视觉模型。")

    tab_photo, tab_manual = st.tabs(["📸 拍照录题", "⌨️ 手动录入"])

    with tab_photo:
        with st.container(border=True):
            col_upload, col_meta = st.columns([3, 2])
            with col_upload:
                uploads = st.file_uploader(
                    "错题图片（支持多选）",
                    type=["jpg", "jpeg", "png", "webp"],
                    accept_multiple_files=True,
                )
            with col_meta:
                tags_input = st.text_input("标签（可选，逗号分隔）", placeholder="例如：期末复习, 几何", key="photo_tags")
                hint = st.text_area(
                    "给老师的话（可选）",
                    placeholder="例如：第二问总是不知道从哪里下手",
                    height=68,
                )

            if uploads and st.button("开始 AI 解析", type="primary", use_container_width=True):
                _process_uploads(service, user, uploads, sanitize_tags(tags_input), hint)

    with tab_manual:
        _render_manual_entry(service, user)


def _render_manual_entry(service, user) -> None:
    """手动录入：没有照片时也能把题目文本归档进错题本（含向量索引）。"""
    with st.container(border=True):
        st.caption("适合已经誊抄/打字的题目，直接录入文字版解析，同样参与语义搜索与相似题召回。")
        with st.form("manual_question_form"):
            content = st.text_area(
                "题目与解析（Markdown，支持 LaTeX）",
                placeholder="### 题目\n已知 $x^2-2(k-1)x+k^2=0$ 有两个实数根，求 $k$ 的取值范围。\n\n### 解析\n由判别式…",
                height=200,
            )
            col_a, col_t, col_k = st.columns([2, 2, 2])
            with col_a:
                answer = st.text_input("正确答案（可选）")
            with col_t:
                tags = st.text_input("标签（逗号分隔）", placeholder="例如：几何, 相似三角形")
            with col_k:
                points = st.text_input("考点（逗号分隔，可选）", placeholder="例如：相似三角形")
            submitted = st.form_submit_button("存入错题本", type="primary", use_container_width=True)
        if submitted:
            if not content.strip():
                st.error("题目与解析不能为空")
                return
            saved = service.create_manual_question(
                user["id"],
                content_markdown=content.strip(),
                answer=answer.strip(),
                tags=sanitize_tags(tags),
                knowledge_points=sanitize_tags(points),
            )
            st.success(f"已存入错题本（#{saved.id}），向量索引同步更新。")


def _process_uploads(service, user, uploads, tags: list[str], hint: str) -> None:
    progress = st.progress(0.0, text="准备解析…")
    results = []
    for idx, upload in enumerate(uploads, 1):
        progress.progress(
            (idx - 1) / len(uploads), text=f"正在解析 {upload.name}（{idx}/{len(uploads)}）"
        )
        try:
            image_bytes = upload.getvalue()
            mime = upload.type or "image/jpeg"
            saved, analysis = service.analyze_and_save(
                user["id"], image_bytes, mime_type=mime, user_tags=tags, hint=hint
            )
            results.append((upload.name, saved, analysis, None))
        except Exception as exc:  # noqa: BLE001 - 单张失败不影响其余
            results.append((upload.name, None, None, str(exc)))
    progress.progress(1.0, text="解析完成")

    ok_count = sum(1 for r in results if r[1] is not None)
    st.success(f"完成：成功 {ok_count} / {len(results)} 张，已自动归档入错题本。")

    if ok_count:
        nav_col, _ = st.columns([1, 2])
        with nav_col:
            if st.button("📒 去错题本查看", type="primary"):
                go_to("notebook")

    for name, saved, analysis, error in results:
        st.markdown(f"##### {name}")
        if error:
            st.error(f"解析失败：{error}")
            continue
        assert saved is not None and analysis is not None
        _render_analysis(saved, analysis, service, user)


def _render_analysis(saved, analysis, service, user) -> None:
    img_col, content_col = st.columns([2, 3])
    with img_col:
        st.image(saved.image_path, use_container_width=True)
        badges = " ".join(f'<span class="mm-badge">{t}</span>' for t in saved.tags)
        st.markdown(
            f"""<div style="margin-top:0.5rem">
            <span class="mm-badge mm-badge--blue">难度：{saved.difficulty}</span>{badges}
            </div>""",
            unsafe_allow_html=True,
        )
    with content_col:
        st.markdown(f"**考点**：{'、'.join(analysis.knowledge_points)}")
        st.markdown(analysis.analysis, unsafe_allow_html=True)
        st.markdown(f"**正确答案**：{analysis.answer}")
        if analysis.mistake_cause:
            st.info(f"常见错因：{analysis.mistake_cause}")
        if analysis.followup_question:
            with st.expander("举一反三 · 变式练习"):
                st.markdown(analysis.followup_question)

        st.divider()
        st.markdown("**相似错题（向量召回）**")
        similar = service.similar_questions(saved, user_id=user["id"])
        if similar:
            for q in similar:
                st.markdown(
                    f"- 🏷️ {'、'.join(q.tags[:3])} · "
                    f"<span class='mm-muted'>{q.content_markdown[:60]}…</span>",
                    unsafe_allow_html=True,
                )
        else:
            st.caption("暂无相似错题。随着错题积累，这里会自动出现同知识点的历史题目。")
