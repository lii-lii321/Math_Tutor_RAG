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


def followup_chat(service, question, user: dict) -> None:
    """围绕一道错题的多轮追问对话组件（历史按题隔离，存于 session_state）。"""
    history_key = f"chat_{question.id}"
    st.session_state.setdefault(history_key, [])

    for message in st.session_state[history_key]:
        with st.chat_message(
            message["role"], avatar="🧑‍🎓" if message["role"] == "user" else "📘"
        ):
            st.markdown(message["content"])

    if prompt := st.chat_input(
        "哪里没看懂？问老师（例如：为什么判别式要大于等于零）",
        key=f"chat_input_{question.id}",
    ):
        st.session_state[history_key].append({"role": "user", "content": prompt})
        with st.chat_message("user", avatar="🧑‍🎓"):
            st.markdown(prompt)
        with st.chat_message("assistant", avatar="📘"):
            try:
                reply = service.answer_followup(
                    question.id, user["id"], st.session_state[history_key], prompt
                )
            except Exception as exc:  # noqa: BLE001 - 对话失败不应崩溃页面
                reply = f"⚠️ 讲师暂时不可用：{exc}"
            st.markdown(reply)
        st.session_state[history_key].append({"role": "assistant", "content": reply})
        st.rerun()


def edit_question_form(service, question, user: dict) -> None:
    """错题编辑表单（错题本与复习页共用）。保存后提示并刷新。"""
    from backend.services.question_service import sanitize_tags

    with st.form(f"edit_form_{question.id}"):
        new_tags = st.text_input(
            "标签（逗号分隔）",
            value="、".join(question.tags) if question.tags else "",
        )
        new_content = st.text_area(
            "解析（Markdown）", value=question.content_markdown, height=260
        )
        new_answer = st.text_input("答案", value=question.answer)
        new_note = st.text_area(
            "我的笔记（易错点、思路备忘）",
            value=question.user_note or "",
            height=80,
            placeholder="例如：下次先看第二问的隐藏条件",
        )
        if st.form_submit_button("保存修改", type="primary"):
            from contextlib import suppress

            updated = service.update_question(
                question.id,
                user["id"],
                content_markdown=new_content,
                answer=new_answer,
                tags=sanitize_tags(new_tags.replace("、", ",")),
                user_note=new_note.strip() or None,
            )
            if updated is None:
                st.error("保存失败：只能编辑自己的错题（教师可查看但不可修改学生的题）")
            else:
                st.success("已保存，向量索引同步更新")
                with suppress(Exception):
                    st.rerun()


def keyboard_shortcuts() -> None:
    """复习页键盘快捷键：空格/回车=显示解析，1/2/3/4=四种评分。

    通过同源组件 iframe 向父页面注册 keydown 监听（Streamlit 重渲染后自动重绑）。
    """
    import streamlit.components.v1 as components

    components.html(
        """
<script>
(function () {
  var doc = window.parent.document;
  if (doc.__mmKeyHandler) { doc.removeEventListener('keydown', doc.__mmKeyHandler); }
  function findByText(txt) {
    var buttons = doc.querySelectorAll('button');
    for (var i = 0; i < buttons.length; i++) {
      if (buttons[i].innerText && buttons[i].innerText.trim() === txt) return buttons[i];
    }
    return null;
  }
  function clickByText(txt) {
    var b = findByText(txt);
    if (b) { b.click(); return true; }
    return false;
  }
  var handler = function (e) {
    var tag = e.target && e.target.tagName;
    if (tag === 'INPUT' || tag === 'TEXTAREA' || e.target.isContentEditable) return;
    if (e.code === 'Space' || e.code === 'Enter') {
      if (clickByText('显示解析')) e.preventDefault();
      return;
    }
    var map = { '1': '😵 忘了', '2': '😅 勉强', '3': '🙂 记得', '4': '😎 秒懂' };
    var label = map[e.key];
    if (label && clickByText(label)) e.preventDefault();
  };
  doc.__mmKeyHandler = handler;
  doc.addEventListener('keydown', handler);
})();
</script>
""",
        height=0,
    )
