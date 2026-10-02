"""可复用的展示组件：错题详情视图、安全调用、错误降级、掌握度原语。"""
from __future__ import annotations

import html

import streamlit as st

from backend.utils.logging import get_logger
from backend.utils.paths import resolve_image_path

logger = get_logger("ui")

GRADE_LABELS = {"again": "😵 忘了", "hard": "😅 勉强", "good": "🙂 记得", "easy": "😎 秒懂"}


def error_card(title: str, detail: str | None = None, *, expander: bool = True) -> None:
    """统一的错误降级卡：用户看到可读文案，原始细节折叠进 expander。"""
    st.error(f"⚠️ {title}")
    if detail and expander:
        with st.expander("技术详情（供排查）"):
            st.code(detail)


def safe_call(fn, *args, error_title: str = "加载失败，请稍后重试", **kwargs):
    """服务调用安全包装：异常转为 error_card 降级，返回 (ok, result)。"""
    try:
        return True, fn(*args, **kwargs)
    except Exception as exc:  # noqa: BLE001 - 页面层兜底，避免 traceback 打屏
        logger.warning("safe_call %s 失败: %s", getattr(fn, "__name__", fn), exc)
        error_card(error_title, str(exc))
        return False, None


def mastery_fill_html(pct: float, color: str = "#2563eb") -> str:
    """掌握度横条的轨道+填充部分（无标签行），pct 为 0~100。"""
    width = max(min(pct, 100), 3)
    return (
        f'<div class="mm-mastery__track">'
        f'<div class="mm-mastery__fill" style="width:{width:.0f}%;background:{color}"></div></div>'
    )


def mastery_bar_html(
    label: str | None, pct: float, color: str = "#2563eb", right: str | None = None
) -> str:
    """完整掌握度横条：左标签 + 右侧文案 + 轨道填充。"""
    left = f"<span>{label}</span>" if label else "<span></span>"
    right_html = f"<span>{right}</span>" if right else ""
    return (
        f'<div class="mm-mastery"><div class="mm-mastery__row">{left}{right_html}</div>'
        + mastery_fill_html(pct, color)
        + "</div>"
    )


def question_detail_view(q, show_hit: bool = True) -> None:
    """错题「查看」视图：原图/元信息/解析/笔记/答案/变式（不含交互）。

    show_hit：搜索场景下展示关键词命中片段预览。
    """
    img_col, content_col = st.columns([2, 3])
    with img_col:
        image_abs = resolve_image_path(q.image_path)
        if image_abs and image_abs.exists():
            st.image(str(image_abs), width="stretch")
        else:
            st.caption("无原图（手动录入）")
        badges = " ".join(f"<span class='mm-badge'>{t}</span>" for t in q.tags)
        st.markdown(
            f"<div><span class='mm-badge mm-badge--blue'>{q.difficulty}</span>{badges}</div>",
            unsafe_allow_html=True,
        )
        if q.reps:
            st.caption(f"已复习 {q.reps} 次 · 间隔 {q.interval_days:.0f} 天 · 难度系数 {q.ease:.2f}")
        else:
            st.caption("尚未复习")
    with content_col:
        if q.user_note:
            st.info(f"📝 我的笔记：{q.user_note}")
        if q.verification_status == "verified":
            st.success(f"✓ 数学一致性已验证（{q.verification_confidence:.0%}）")
        elif q.verification_status == "failed":
            st.warning("⚠️ 验证未通过：答案疑似有误，请人工确认")
        elif q.verification_status == "uncertain":
            st.caption("⚠️ 当前答案无法自动验证，请人工确认")
        st.markdown(q.content_markdown, unsafe_allow_html=True)
        if q.answer:
            st.markdown(f"**答案**：{q.answer}")
        with st.expander("📋 复制 / 分享本题"):
            plain = q.content_markdown
            if q.answer:
                plain = f"{plain}\n\n**答案**：{q.answer}"
            st.code(plain, language=None)
            st.caption("点击代码块右上角复制图标即可全文复制，适合粘贴到笔记或打印。")
        _hit_preview(q)
        if q.followup_question:
            with st.expander("举一反三 · 变式练习"):
                st.markdown(q.followup_question)


def _hit_preview(q) -> None:
    """展示搜索关键词的首个命中片段（转义后高亮，不改动原解析渲染）。"""
    keyword = st.session_state.get("notebook_search")
    if not keyword:
        return
    kw = keyword.strip()
    if not kw:
        return
    for source in (q.content_markdown, q.answer or "", q.ocr_text or ""):
        lowered = source.lower()
        pos = lowered.find(kw.lower())
        if pos < 0:
            continue
        start = max(0, pos - 30)
        end = min(len(source), pos + len(kw) + 30)
        fragment = source[start:end]
        highlighted = re_escape_and_mark(fragment, kw)
        st.markdown(
            f"🔍 命中：<span style='background:#fef3c7;border-radius:4px'>"
            f"{highlighted}</span>",
            unsafe_allow_html=True,
        )
        return


def re_escape_and_mark(fragment: str, keyword: str) -> str:
    """HTML 转义后高亮关键词（大小写不敏感）。"""
    import re

    escaped_kw = re.escape(keyword)
    marked = re.sub(
        escaped_kw,
        lambda m: f"<mark>{html.escape(m.group(0))}</mark>",
        html.escape(fragment),
        flags=re.IGNORECASE,
    )
    return marked.replace("\n", " ")


def regrade_buttons(service, q, user: dict) -> None:
    """单题重测：按 SM-2 对本题直接评分（教师操作他人题目会得到提示）。"""
    st.markdown("**重测本题**")
    grade_cols = st.columns(4)
    for col, grade in zip(grade_cols, ("again", "hard", "good", "easy"), strict=False):
        with col:
            if st.button(
                GRADE_LABELS[grade], key=f"nb_grade_{q.id}_{grade}", width="stretch"
            ):
                updated = service.grade_review(q.id, user["id"], grade)
                if updated is None:
                    st.toast("只能重测自己的错题", icon="⚠️")
                else:
                    st.toast("已按 SM-2 重新排期", icon="🔁")
                st.rerun()


def save_followup_button(service, q, user: dict, followup: str) -> None:
    """把变式练习一键存为新的待做错题（继承原题标签并追加「变式练习」）。"""
    if not followup:
        return
    if st.button("📥 把变式题存入错题本", key=f"save_followup_{q.id}"):
        tags = [*(q.tags or []), "变式练习"]
        saved = service.create_manual_question(
            user["id"],
            content_markdown=f"### 变式练习（来自错题 #{q.id}）\n\n{followup}",
            tags=tags,
            source="followup",
        )
        st.success(f"已存入错题本（#{saved.id}），进入正常复习循环。")
