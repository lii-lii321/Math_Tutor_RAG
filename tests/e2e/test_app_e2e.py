"""E2E 冒烟测试（Playwright headless）。

运行方式（需先启动应用）：
    set MM_E2E=1 && pytest tests/e2e -q -m e2e

CI 中由 boot-smoke job 先拉起应用再执行。
"""
from __future__ import annotations

import os
import time

import pytest

try:
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
except ImportError:  # 非 E2E 环境（未安装 playwright）仅收集不运行
    PlaywrightTimeoutError = TimeoutError  # type: ignore[misc,assignment]

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
    page.wait_for_selector("text=累计错题", timeout=30000)


def _wait_any_text(page, markers: list[str], timeout_ms: int) -> None:
    """轮询直到任一文本可见（Playwright 的逗号 OR 选择器对 text= 不可靠）。"""
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        for marker in markers:
            if page.locator(f"text={marker}").first.is_visible():
                return
        page.wait_for_timeout(500)
    page.screenshot(path="e2e_failure.png")
    raise PlaywrightTimeoutError(f"均未出现：{markers}")


def _goto(page, label: str, marker: str | None = None, timeout: int = 30000) -> None:
    """点击侧边栏菜单（组件在 iframe 内），并等待目标页标志出现。"""
    page.wait_for_timeout(1200)
    frame = page.frame_locator("iframe[title*='streamlit_antd_components']").first
    frame.get_by_text(label, exact=True).click()
    if marker:
        _wait_any_text(page, marker.split("|"), timeout)


def test_login_and_dashboard(page):
    _login(page, "demo", "demo123")
    assert page.locator("text=累计错题").first.is_visible()


def test_navigate_all_pages(page):
    _login(page, "demo", "demo123")
    _goto(page, "错题本", "语义搜索")
    _goto(page, "知识图谱", "标签共现网络|错题数量还太少")
    _goto(page, "设置", "AI 引擎")


def test_teacher_sees_students_overview(page):
    _login(page, "admin", "admin123")
    _goto(page, "学生总览", "学生总数")
