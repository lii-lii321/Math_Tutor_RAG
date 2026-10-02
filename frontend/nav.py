"""导航注册表：页面 key 与侧边栏标签的唯一来源。

只依赖 frontend.i18n，避免与 app.py / frontend.common 循环导入；
app.py 的侧边栏表与 frontend.common.go_to 的解析均由此派生。
"""
from __future__ import annotations

from dataclasses import dataclass

from frontend.i18n import t


@dataclass(frozen=True)
class NavPage:
    """一个侧边栏导航项。"""

    key: str
    label: str
    teacher_only: bool = False
    group: str = "learn"  # today / learn / explore —— 侧边栏三组分层


# 有序注册表，即侧边栏展示顺序；teacher_only 项由 app.py 插在「知识图谱」之前
PAGES: tuple[NavPage, ...] = (
    NavPage("dashboard", t("nav.dashboard"), group="today"),
    NavPage("review", t("nav.review"), group="today"),
    NavPage("tutor", t("nav.tutor"), group="learn"),
    NavPage("notebook", t("nav.notebook"), group="learn"),
    NavPage("mastery", t("nav.mastery"), group="learn"),
    NavPage("students", t("nav.students"), teacher_only=True, group="learn"),
    NavPage("graph", t("nav.graph"), group="explore"),
    NavPage("assistant", t("nav.assistant"), group="explore"),
    NavPage("settings", t("nav.settings"), group="explore"),
)

PAGE_KEYS: frozenset[str] = frozenset(page.key for page in PAGES)

GROUP_LABELS: dict[str, str] = {"today": "今天", "learn": "学习", "explore": "探索"}


def resolve_label(page_key: str) -> str:
    """页面 key → 侧边栏标签；未注册的 key 抛 KeyError 而非 StopIteration。"""
    for page in PAGES:
        if page.key == page_key:
            return page.label
    raise KeyError(f"未注册的导航页 key：{page_key}")
