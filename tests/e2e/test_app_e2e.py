"""E2E 冒烟测试（Playwright headless）。

运行方式（需先启动应用）：
    pytest tests/e2e -q -m e2e --e2e-base-url http://localhost:8601

CI 中由 boot-smoke job 先拉起应用再执行；本地可手动复现。
"""
from __future__ import annotations

import os

import pytest

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
        os.getenv("MM_E2E", "") != "1",
        reason="E2E 需要运行中的应用与浏览器：MM_E2E=1 pytest tests/e2e",
    ),
]

BASE_URL = os.getenv("MM_E2E_BASE_URL", "http://localhost:8601")


def _login(page, username: str, password: str) -> None:
    page.goto(BASE_URL)
    page.wait_for_selector("input", timeout=30000)
    inputs = page.locator('input[type="text"], input[type="password"]')
    inputs.nth(0).fill(username)
    inputs.nth(1).fill(password)
    page.get_by_role("button", name="登录", exact=True).first.click(force=True)
    page.wait_for_timeout(6000)


def _goto(page, label: str) -> None:
    """点击侧边栏菜单（组件在 iframe 内）。"""
    page.wait_for_timeout(1500)
    frame = page.frame_locator("iframe[title*='streamlit_antd_components']").first
    frame.get_by_text(label, exact=True).click()
    page.wait_for_timeout(5000)


def test_login_and_dashboard(page):
    _login(page, "demo", "demo123")
    assert page.locator("text=累计错题").first.is_visible()
    assert page.locator("text=今日复习").first.is_visible() or page.locator(
        "text=待复习"
    ).first.is_visible()


def test_navigate_all_pages(page):
    _login(page, "demo", "demo123")
    for label, marker in [
        ("错题本", "语义搜索"),
        ("知识图谱", "标签共现网络"),
        ("设置", "AI 引擎"),
    ]:
        _goto(page, label)
        assert page.locator(f"text={marker}").first.is_visible(), f"{label} 未渲染"


def test_teacher_sees_students_overview(page):
    _login(page, "admin", "admin123")
    _goto(page, "学生总览")
    assert page.locator("text=学生总数").first.is_visible()
