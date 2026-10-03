"""AI 助手页：自然语言驱动的错题本 AI Tutor 对话。

演示模式（无 API Key）下提供本地规则应答，保证零配置可体验；
配置 Key 后由 OpenAI function calling 循环驱动真实工具调用。
Batch 07：对话服务端持久化——可切换/恢复历史对话，跨端继续学习。
"""
from __future__ import annotations

import streamlit as st

from backend.config import get_settings
from backend.services.question_service import QuestionService
from frontend.common import get_question_service, page_header


def _demo_reply(user_message: str, service: QuestionService, user: dict) -> str:
    """无 Key 时的本地规则应答：覆盖最常见的三类意图。"""
    from frontend.components import safe_call

    message = user_message.lower()
    if any(word in message for word in ("周报", "本周", "报告")):
        ok, stats = safe_call(
            service.dashboard_stats, user["id"], error_title="学情数据加载失败"
        )
        if not ok:
            return "⚠️ 学情数据暂时加载失败，请稍后再试。"
        weekly = stats["weekly"]
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
        ok, due = safe_call(service.due_questions, user["id"], error_title="复习队列加载失败")
        if not ok:
            return "⚠️ 复习队列暂时加载失败，请稍后再试。"
        if not due:
            return "🎉 今日复习任务已清空，错题本处于健康状态。"
        lines = "\n".join(
            f"- #{q.id}　{'、'.join(q.tags[:3])}　·　{q.difficulty}" for q in due[:8]
        )
        return f"📌 **今日待复习 {len(due)} 题**：\n{lines}\n\n（演示模式，去「今日复习」页开始）"
    if any(word in message for word in ("搜索", "找", "查")):
        keyword = message.replace("搜索", "").replace("找", "").replace("查", "").strip()
        ok, hits = safe_call(
            service.list_questions, user["id"], keyword=keyword or None,
            error_title="搜索失败",
        )
        if not ok:
            return "⚠️ 搜索暂时不可用，请稍后再试。"
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


def _conversation_bar(user: dict, history_key: str, agent_key: str) -> None:
    """历史对话选择条：新建 / 恢复（仅 Agent 模式，演示模式无服务端会话）。"""
    from backend.services.conversation_service import ConversationService

    conversations = ConversationService().list_for_user(user["id"], limit=20)
    cols = st.columns([3, 1])
    with cols[0]:
        options = {"（当前对话）": None}
        options.update(
            {
                f"{c['title']}（{c['message_count']} 条）": c["id"]
                for c in conversations
            }
        )
        current = st.session_state.get(f"agent_conv_id_{user['id']}")
        default_label = next(
            (label for label, cid in options.items() if cid == current), "（当前对话）"
        )
        labels = list(options)
        picked = st.selectbox(
            "历史对话",
            labels,
            index=labels.index(default_label) if default_label in labels else 0,
            label_visibility="collapsed",
        )
    with cols[1]:
        new_chat = st.button("🆕 新对话", width="stretch")

    if new_chat:
        conversation = ConversationService().create(user["id"])
        st.session_state[f"agent_conv_id_{user['id']}"] = conversation["id"]
        st.session_state[history_key] = []
        st.session_state.pop(agent_key, None)
        st.rerun()

    picked_id = options.get(picked)
    if picked_id and picked_id != current:
        st.session_state[f"agent_conv_id_{user['id']}"] = picked_id
        history = ConversationService().history_for_agent(picked_id, user["id"]) or []
        st.session_state[history_key] = list(history)
        st.session_state.pop(agent_key, None)
        st.rerun()


def render_assistant_page(user: dict) -> None:
    service = get_question_service()
    settings = get_settings()
    page_header("AI 助手", "自然语言驱动错题本 · Agent 自主编排工具调用 · 对话云端留存")

    demo = not settings.ai_api_key
    if demo:
        st.markdown('<span class="mm-badge mm-badge--warn">演示模式 · 本地规则应答</span>', unsafe_allow_html=True)
    else:
        st.markdown(
            f'<span class="mm-badge mm-badge--ok">AI Tutor · {settings.ai_model}</span>',
            unsafe_allow_html=True,
        )

    history_key = f"agent_chat_{user['id']}"
    agent_key = f"agent_session_{user['id']}"
    st.session_state.setdefault(history_key, [])

    if not demo:
        _conversation_bar(user, history_key, agent_key)

    for message in st.session_state[history_key]:
        with st.chat_message(message["role"], avatar="🧑‍🎓" if message["role"] == "user" else "🤖"):
            st.markdown(message["content"])

    quick_prompt = None
    if not st.session_state[history_key]:
        st.caption("可以这样开始：")
        chip_cols = st.columns(3)
        with chip_cols[0]:
            if st.button("🔍 我最近哪里最薄弱？", width="stretch"):
                quick_prompt = "我最近哪里最薄弱？帮我分析一下并给出建议。"
        with chip_cols[1]:
            if st.button("📝 生成 5 题练习卷", width="stretch"):
                quick_prompt = "根据我的薄弱知识点生成 5 道题的练习卷。"
        with chip_cols[2]:
            if st.button("📅 今天的复习安排", width="stretch"):
                quick_prompt = "今天的复习计划是什么？"

    prompt = st.chat_input("例如：我最近哪里最薄弱？/ 生成 5 题练习卷 / 搜索 判别式")
    prompt = prompt or quick_prompt
    if prompt:
        st.session_state[history_key].append({"role": "user", "content": prompt})
        with st.chat_message("user", avatar="🧑‍🎓"):
            st.markdown(prompt)
        with st.chat_message("assistant", avatar="🤖"):
            if demo:
                reply = _demo_reply(prompt, service, user)
                st.markdown(reply)
            else:
                from backend.services.agent import AgentSession

                if agent_key not in st.session_state:
                    conversation_id = st.session_state.get(f"agent_conv_id_{user['id']}")
                    if conversation_id is None:
                        from backend.services.conversation_service import ConversationService

                        conversation = ConversationService().create(user["id"])
                        st.session_state[f"agent_conv_id_{user['id']}"] = conversation["id"]
                        conversation_id = conversation["id"]
                    st.session_state[agent_key] = AgentSession(
                        user_id=user["id"], conversation_id=conversation_id
                    )
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
