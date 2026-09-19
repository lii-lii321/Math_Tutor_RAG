"""AI 助手页：自然语言驱动的错题本 Agent 对话。

演示模式（无 API Key）下提供本地规则应答，保证零配置可体验；
配置 Key 后由 OpenAI function calling 循环驱动真实工具调用。
"""
from __future__ import annotations

import streamlit as st

from backend.config import get_settings
from backend.services.question_service import QuestionService
from frontend.common import get_question_service, page_header


def _demo_reply(user_message: str, service: QuestionService, user: dict) -> str:
    """无 Key 时的本地规则应答：覆盖最常见的三类意图。"""
    message = user_message.lower()
    if any(word in message for word in ("周报", "本周", "报告")):
        weekly = service.dashboard_stats(user["id"])["weekly"]
        accuracy = f"{weekly['accuracy']}%" if weekly.get("accuracy") is not None else "—"
        return (
            f"📣 **本周学习概况**（演示模式）\n\n"
            f"- 录入错题：**{weekly['created']}** 题\n"
            f"- 完成复习：**{weekly['reviews']}** 次\n"
            f"- 复习正确率：**{accuracy}**\n"
            f"- 活跃天数：**{weekly['active_days']}** 天\n\n"
            f"配置 `AI_API_KEY` 后，我可以帮你搜题、录题、安排复习。"
        )
    if any(word in message for word in ("到期", "待复习", "今天复习")):
        due = service.due_questions(user["id"])
        if not due:
            return "🎉 今日复习任务已清空，错题本处于健康状态。"
        lines = "\n".join(
            f"- #{q.id}　{'、'.join(q.tags[:3])}　·　{q.difficulty}" for q in due[:8]
        )
        return f"📌 **今日待复习 {len(due)} 题**：\n{lines}\n\n（演示模式，去「今日复习」页开始）"
    if any(word in message for word in ("搜索", "找", "查")):
        keyword = message.replace("搜索", "").replace("找", "").replace("查", "").strip()
        hits = service.list_questions(user["id"], keyword=keyword or None)
        if not hits:
            return f"没有找到与「{keyword}」相关的错题。"
        lines = "\n".join(f"- #{q.id}　{'、'.join(q.tags[:3])}" for q in hits[:8])
        return f"🔍 找到 {len(hits)} 道相关错题：\n{lines}"
    return (
        "👋 我是错题本助手（**演示模式**）。\n\n"
        "可以试试问我：\n"
        "- 「本周学习报告」\n"
        "- 「今天有哪些要复习的」\n"
        "- 「搜索 判别式」\n\n"
        "配置 `AI_API_KEY` 后，我能真正调用错题本工具——搜索、录题、评分、组卷一一句话完成。"
    )


def render_assistant_page(user: dict) -> None:
    service = get_question_service()
    settings = get_settings()
    page_header("AI 助手", "自然语言驱动错题本 · Agent 自主编排工具调用")

    demo = not settings.ai_api_key
    if demo:
        st.markdown('<span class="mm-badge mm-badge--warn">演示模式 · 本地规则应答</span>', unsafe_allow_html=True)
    else:
        st.markdown(
            f'<span class="mm-badge mm-badge--ok">Agent 模式 · {settings.ai_model}</span>',
            unsafe_allow_html=True,
        )

    history_key = f"agent_chat_{user['id']}"
    st.session_state.setdefault(history_key, [])

    for message in st.session_state[history_key]:
        with st.chat_message(message["role"], avatar="🧑‍🎓" if message["role"] == "user" else "🤖"):
            st.markdown(message["content"])

    if prompt := st.chat_input("例如：本周学习报告 / 今天有哪些要复习的 / 搜索 判别式"):
        st.session_state[history_key].append({"role": "user", "content": prompt})
        with st.chat_message("user", avatar="🧑‍🎓"):
            st.markdown(prompt)
        with st.chat_message("assistant", avatar="🤖"):
            if demo:
                reply = _demo_reply(prompt, service, user)
                st.markdown(reply)
            else:
                from backend.services.agent import AgentSession

                agent_key = f"agent_session_{user['id']}"
                if agent_key not in st.session_state:
                    st.session_state[agent_key] = AgentSession(user_id=user["id"])
                try:
                    # 流式输出：Agent 的文本增量直接打进聊天气泡
                    reply = st.write_stream(st.session_state[agent_key].chat_stream(prompt))
                except Exception as exc:  # noqa: BLE001 - 对话失败不崩溃页面
                    reply = f"⚠️ Agent 暂时不可用：{exc}"
                    st.markdown(reply)
        st.session_state[history_key].append({"role": "assistant", "content": reply})
        st.rerun()


def _is_demo(settings) -> bool:
    return not settings.ai_api_key
