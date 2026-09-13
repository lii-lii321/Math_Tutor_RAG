"""轻量 i18n：集中管理界面文案，当前提供 zh（默认）。

用法：from frontend.i18n import t; t("nav.dashboard")
新增语言：复制 STRINGS 为新语言键并翻译；缺键时回退 zh。
"""
from __future__ import annotations

STRINGS: dict[str, dict[str, str]] = {
    "zh": {
        "app.tagline": "视觉大模型 × RAG 错题本",
        "nav.dashboard": "学情看板",
        "nav.tutor": "AI 录题",
        "nav.notebook": "错题本",
        "nav.review": "今日复习",
        "nav.graph": "知识图谱",
        "nav.students": "学生总览",
        "nav.settings": "设置",
        "nav.logout": "退出登录",
        "page.dashboard.title": "学情看板",
        "page.tutor.title": "AI 录题",
        "page.notebook.title": "错题本",
        "page.review.title": "今日复习",
        "page.graph.title": "知识图谱",
        "page.students.title": "学生总览",
        "page.settings.title": "设置",
        "action.start_review": "🎬 开始复习",
        "action.add_question": "📸 录一道错题",
        "action.open_notebook": "📒 打开错题本",
    },
}

DEFAULT_LANG = "zh"


def t(key: str, lang: str = DEFAULT_LANG) -> str:
    """取文案；缺失时回退默认语言，再缺失则返回 key 本身。"""
    return STRINGS.get(lang, STRINGS[DEFAULT_LANG]).get(key, key)
