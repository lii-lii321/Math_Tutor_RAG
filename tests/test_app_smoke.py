"""应用级冒烟（Streamlit AppTest）：登录 → 看板渲染零异常。

与 Playwright E2E 的分工：AppTest 在进程内跑真实 app.py，无需浏览器，
回归快且能在 CI 的 test job 里跑（E2E 仅 boot-smoke job 可跑）。
回归价值实证：本文件编写时即抓到「看板重复渲染热力图导致
StreamlitDuplicateElementId」的生产 bug。
"""
from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

_APP_ENTRY = Path(__file__).resolve().parent.parent / "app.py"


@pytest.fixture
def demo_credentials() -> tuple[str, str]:
    """取种子 demo 账号（口令可被环境变量覆盖，硬编码会漂移）。"""
    from backend.config import get_settings

    settings = get_settings()
    return settings.seed_demo_username, settings.seed_demo_password


def _fill_and_login(at: AppTest, username: str, password: str) -> None:
    filled = 0
    for ti in at.text_input:
        if ti.label == "用户名":
            ti.set_value(username)
            filled += 1
        elif ti.label == "密码":
            ti.set_value(password)
            filled += 1
    assert filled == 2, f"登录表单字段不完整（找到 {filled}/2）"
    clicked = False
    for b in at.button:
        if b.label == "登录":
            b.click()
            clicked = True
            break
    assert clicked, "未找到登录提交按钮"
    at.run()


def test_app_boots_to_login_page():
    at = AppTest.from_file(_APP_ENTRY, default_timeout=120)
    at.run()
    assert not at.exception
    labels = [tb.label for tb in at.tabs]
    assert "登录" in labels
    assert "注册" in labels


def test_app_login_and_dashboard_render(demo_credentials):
    username, password = demo_credentials
    at = AppTest.from_file(_APP_ENTRY, default_timeout=180)
    at.run()
    _fill_and_login(at, username, password)

    assert not at.exception, f"登录后看板异常: {[str(e.value) for e in at.exception]}"
    # session 中已写入登录用户
    user = dict(at.session_state["user"])
    assert user["username"] == username
    # 看板渲染出行动按钮与退出入口
    btn_labels = [b.label for b in at.button]
    assert any("开始今日复习" in label for label in btn_labels)
    assert "退出登录" in btn_labels


def test_app_login_rejects_wrong_password(demo_credentials):
    username, _ = demo_credentials
    at = AppTest.from_file(_APP_ENTRY, default_timeout=120)
    at.run()
    _fill_and_login(at, username, "wrong-password-123")

    assert not at.exception
    # 未登录：session 无 user，页面仍停在登录表单
    assert "user" not in at.session_state
    errors = [str(e.value) for e in at.error]
    assert errors, "错误口令应给出可读错误提示"
