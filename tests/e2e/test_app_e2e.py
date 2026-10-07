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
    _goto(page, "能力画像", "知识点掌握度|还没有知识点数据")
    _goto(page, "知识图谱", "标签共现网络|错题数量还太少")
    # 与提供商无关：演示模式徽章或 AI Tutor 徽章都算到达
    _goto(page, "Ai 助手", "演示模式|AI Tutor")
    _goto(page, "设置", "AI 引擎")


def test_teacher_sees_students_overview(page):
    _login(page, "admin", "admin123")
    _goto(page, "学生总览", "学生总数")


def test_notebook_url_filter_survives_reload(page):
    """错题本关键词筛选写入 URL；浏览器刷新即新会话（登录态在 session），
    重新登录后首帧不清理 URL，再进错题本从 URL 回种筛选——穿登录可达的
    完整浏览器语义（AppTest 测不了，批 B 发布条件手动项自动化）。"""
    _login(page, "demo", "demo123")
    _goto(page, "错题本", "语义搜索")
    keyword = "zz_reload_probe_zz"
    search = page.get_by_placeholder("搜索错题（自然语言即可）")
    search.fill(keyword)
    search.press("Enter")
    _wait_any_text(page, [f"搜索:{keyword}"], 20000)  # chip 回显 = 本轮已按关键词过滤
    assert "nb_kw=" in page.url, "筛选后 URL 应携带 nb_kw"

    page.reload()  # 刷新即新会话：回到登录页，但浏览器 URL 参数仍在
    page.wait_for_selector("input", timeout=30000)
    assert "nb_kw=" in page.url, "刷新后 URL 参数不应丢失"
    inputs = page.locator('input[type="text"], input[type="password"]')
    inputs.nth(0).fill("demo")
    inputs.nth(1).fill("demo123")
    page.get_by_role("button", name="登录", exact=True).first.click(force=True)
    page.wait_for_selector("text=累计错题", timeout=30000)
    assert "nb_kw=" in page.url, "登录后首帧（落看板）不应清理 URL 参数"

    _goto(page, "错题本", f"搜索:{keyword}", 30000)  # 进错题本：从 URL 回种筛选
    search_after = page.get_by_placeholder("搜索错题（自然语言即可）")
    search_after.wait_for(state="visible", timeout=30000)
    assert search_after.input_value() == keyword, "重进后搜索框应从 URL 回种关键词"


def test_dashboard_milestone_badge_wall_visible(page):
    """登录后看板渲染里程碑徽章墙区块（已达成 pill + 待解锁计数）。"""
    _login(page, "demo", "demo123")
    _wait_any_text(page, ["里程碑"], 30000)


def test_settings_full_backup_button_visible_and_triggers(page):
    """设置页「生成完整备份」按钮可见可触发：点击后 ZIP 下载按钮就绪。"""
    _login(page, "demo", "demo123")
    _goto(page, "设置", "账号")
    generate_btn = page.get_by_role("button", name="生成完整备份")
    generate_btn.wait_for(state="visible", timeout=30000)
    generate_btn.click()
    download_btn = page.get_by_role("button", name="导出完整备份 (ZIP)")
    download_btn.wait_for(state="visible", timeout=30000)
    deadline = time.monotonic() + 20  # 等下一次 rerun 把下载按钮置为可用
    while time.monotonic() < deadline and not download_btn.is_enabled():
        page.wait_for_timeout(500)
    assert download_btn.is_enabled()
