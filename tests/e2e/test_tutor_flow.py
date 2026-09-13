"""E2E：AI 录题全流程与追问对话（mock 提供商，无需真实 API Key）。"""
from __future__ import annotations

import os
import time

import pytest

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(os.getenv("MM_E2E", "") != "1", reason="需要 MM_E2E=1 与运行中的应用"),
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


def _goto(page, label: str, marker: str | None = None, timeout: int = 30000) -> None:
    page.wait_for_timeout(1200)
    frame = page.frame_locator("iframe[title*='streamlit_antd_components']").first
    frame.get_by_text(label, exact=True).click()
    if marker:
        deadline = time.monotonic() + timeout / 1000
        while time.monotonic() < deadline:
            if page.locator(f"text={marker}").first.is_visible():
                return
            page.wait_for_timeout(500)
        page.screenshot(path=f"e2e_failure_{label}.png")
        raise AssertionError(f"{label} 页面未出现标志：{marker}")


@pytest.fixture(scope="module")
def _sample_jpeg(tmp_path_factory):
    from PIL import Image

    image = Image.new("RGB", (40, 30), (170, 200, 240))
    path = tmp_path_factory.mktemp("upload") / "sample.jpg"
    image.save(path, format="JPEG")
    return str(path)


def test_full_tutor_flow(page, _sample_jpeg):
    """上传 → AI 解析（mock）→ 归档 → 错题本可见。"""
    _login(page, "demo", "demo123")
    _goto(page, "Ai 录题", "拍照录题")  # 菜单 format_func='title' 渲染为「Ai 录题」

    file_input = page.locator('input[type="file"]').first
    file_input.set_input_files(_sample_jpeg)
    page.get_by_role("button", name="开始 AI 解析").first.click()

    # mock 提供商固定返回含这些字段的解析
    page.wait_for_selector("text=正确答案", timeout=30000)
    page.wait_for_selector("text=去错题本查看", timeout=15000)

    _goto(page, "错题本", "语义搜索")
    # mock 解析标志在折叠面板内（rerun 后隐藏），attached 即可证明归档成功
    page.wait_for_selector("text=演示模式", timeout=15000, state="attached")


def test_followup_chat_on_question(page, _sample_jpeg):
    """先确保有一道题（录题流程），再在错题本里发一条追问。"""
    _login(page, "demo", "demo123")
    _goto(page, "Ai 录题", "拍照录题")
    file_input = page.locator('input[type="file"]').first
    file_input.set_input_files(_sample_jpeg)
    page.get_by_role("button", name="开始 AI 解析").first.click()
    page.wait_for_selector("text=正确答案", timeout=30000)

    _goto(page, "错题本", "语义搜索")
    page.wait_for_timeout(1500)
    # 展开第一题并切到追问讲题（Streamlit DOM 上用 JS 触发最可靠）
    page.evaluate(
        """(() => {
          const s = [...document.querySelectorAll('summary')].find(x => x.innerText.includes('⏰'));
          if (s) s.click();
        })()"""
    )
    page.wait_for_timeout(3000)
    page.evaluate(
        """(() => {
          const t = [...document.querySelectorAll('button[data-baseweb="tab"]')]
            .find(x => x.innerText.includes('追问讲题'));
          if (t) t.click();
        })()"""
    )
    page.wait_for_timeout(2500)

    page.evaluate(
        """(() => {
          const ta = document.querySelector('div[data-testid="stChatInput"] textarea');
          if (!ta) return;
          const setter = Object.getOwnPropertyDescriptor(
            window.HTMLTextAreaElement.prototype, 'value').set;
          setter.call(ta, '为什么判别式要大于等于零？');
          ta.dispatchEvent(new Event('input', { bubbles: true }));
          ta.dispatchEvent(new KeyboardEvent('keydown', {
            key: 'Enter', code: 'Enter', keyCode: 13, bubbles: true }));
        })()"""
    )
    # 发送后 st.rerun 会重新折叠面板 → 回复在 DOM 中但隐藏，attached 即可
    page.wait_for_selector("text=已收到你的追问", timeout=30000, state="attached")
