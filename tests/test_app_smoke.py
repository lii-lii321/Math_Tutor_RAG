"""应用级冒烟（Streamlit AppTest）：登录 → 看板渲染零异常。

与 Playwright E2E 的分工：AppTest 在进程内跑真实 app.py，无需浏览器，
回归快且能在 CI 的 test job 里跑（E2E 仅 boot-smoke job 可跑）。
回归价值实证：本文件编写时即抓到「看板重复渲染热力图导致
StreamlitDuplicateElementId」的生产 bug。
"""
from __future__ import annotations

import secrets
import uuid
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

_APP_ENTRY = Path(__file__).resolve().parent.parent / "app.py"
# 测试夹具账号的口令每次会话随机生成，源码零硬编码凭据
_SMOKE_PASSWORD = secrets.token_urlsafe(12)


@pytest.fixture
def demo_credentials() -> tuple[str, str]:
    """取种子 demo 账号（口令可被环境变量覆盖，硬编码会漂移）。"""
    from backend.config import get_settings

    settings = get_settings()
    return settings.seed_demo_username, settings.seed_demo_password


@pytest.fixture
def service():
    from backend.database import SessionLocal
    from backend.services.question_service import QuestionService

    return QuestionService(session_factory=SessionLocal)


@pytest.fixture
def smoke_user(db_session):
    """独立账号（uuid 后缀 + 随机口令），避免污染种子 demo 用户的数据面。"""
    from backend.models.orm import User
    from backend.utils.security import hash_password

    user = User(
        username=f"nburl_{uuid.uuid4().hex[:8]}",
        password_hash=hash_password(_SMOKE_PASSWORD, 4),
        role="student",
    )
    db_session.add(user)
    db_session.commit()
    return user


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


def _goto_page(at: AppTest, label: str) -> None:
    """AppTest 侧边栏导航：走生产 go_to 同款 _pending_nav 消费机制
    （app.py 会按当前徽标状态归一菜单标签后再实例化 sac.menu；
    先解除旧 nav 绑定，避免 AppTest 无前端回传时组件值滞留）。"""
    try:
        del at.session_state["nav"]
    except KeyError:
        pass
    at.session_state["_pending_nav"] = label
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
    # 里程碑徽章墙（C2）随 KPI 行渲染，零异常（含未达成置灰计数）
    assert any("里程碑" in str(m.value) for m in at.markdown)


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


# ---------- 错题本筛选进 URL：穿登录可达 / 离开即清 / 回调写回 ----------

def _seed_question(service, user_id: int, content: str, answer: str, tag: str):
    """种子只建用户不建题：先经 service 建题，否则队列/检索为空、断言空转。"""
    return service.create_manual_question(
        user_id,
        content_markdown=content,
        answer=answer,
        tags=[tag],
    )


def test_notebook_url_params_through_login_and_leave_clear(smoke_user, service):
    """带 nb_* 参数的 URL 未登录打开 → 登录（首帧落看板不清理）→
    进错题本筛选生效渲染零异常；离开即清 URL 与控件会话键，再进为默认视图。"""
    _seed_question(
        service, smoke_user.id, "二次函数顶点式迁移题", "y = a(x-h)² + k", "url冒烟"
    )
    at = AppTest.from_file(_APP_ENTRY, default_timeout=180)
    at.query_params["nb_kw"] = "二次函数"  # 模拟分享链接（未登录新窗口打开）
    at.run()
    assert not at.exception
    _fill_and_login(at, smoke_user.username, _SMOKE_PASSWORD)
    assert not at.exception
    # 登录后首帧恒落看板，且首帧（无 _last_page 标记）不清理 URL 参数
    assert dict(at.session_state["user"])["username"] == smoke_user.username
    assert at.query_params.get("nb_kw") == ["二次函数"]
    # 全局搜索框（st.form 包裹）已随侧边栏就位
    assert any(ti.label == "全局搜索" for ti in at.text_input)

    _goto_page(at, "错题本")
    assert not at.exception, [str(e.value) for e in at.exception]
    # URL 关键词已种入搜索框；结果非空（导出按钮仅在检索命中时渲染）
    searches = [ti for ti in at.text_input if ti.label == "搜索"]
    assert searches and searches[0].value == "二次函数"
    assert any("导出" in d.label for d in at.download_button)
    # 默认值不写 URL：URL 里只携带显式带入的 nb_kw
    assert list(at.query_params.keys()) == ["nb_kw"]

    # 迁移门控：离开错题本那一帧，URL 参数与控件会话键同步复位
    _goto_page(at, "学情看板")
    assert not at.exception
    assert "nb_kw" not in at.query_params
    assert "notebook_search" not in at.session_state

    # 再进为默认视图
    _goto_page(at, "错题本")
    assert not at.exception
    searches = [ti for ti in at.text_input if ti.label == "搜索"]
    assert searches and searches[0].value == ""
    assert any("导出" in d.label for d in at.download_button)

    # on_change 回调写回：改搜索框 → URL 即时携带 nb_kw
    searches[0].set_value("顶点式").run()
    assert not at.exception
    assert at.query_params.get("nb_kw") == ["顶点式"]

    # 清除全部筛选按钮：控件会话键与 URL 同步清除
    clear_btn = [b for b in at.button if b.label == "✕ 清除全部筛选"]
    assert clear_btn, "有关键词 chip 时应渲染清除按钮"
    clear_btn[0].click()
    at.run()
    assert not at.exception
    assert "nb_kw" not in at.query_params
    # 控件重实例化后键会以默认值回写，断言搜索框回到空值而非键消失
    searches = [ti for ti in at.text_input if ti.label == "搜索"]
    assert searches and searches[0].value == ""


# ---------- 复习页三路径 + fragment 交互 ----------

def test_review_page_three_paths(smoke_user, service):
    """复习页三路径：mode=plan 计划桥接 / mode=due 到期桥接 / 菜单直达。"""
    _seed_question(
        service,
        smoke_user.id,
        "复习三路径冒烟题：判别式分类讨论",
        "Δ ≥ 0",
        "复习冒烟",
    )
    at = AppTest.from_file(_APP_ENTRY, default_timeout=180)
    at.run()
    _fill_and_login(at, smoke_user.username, _SMOKE_PASSWORD)

    # 路径一：go_to(mode="plan") 桥接 → 计划模式队列
    at.session_state["param_mode"] = "plan"
    _goto_page(at, "今日复习")
    assert not at.exception, [str(e.value) for e in at.exception]
    assert any("计划模式" in str(m.value) for m in at.markdown)
    assert any(b.label == "显示解析" for b in at.button), "计划队列为空，断言空转"

    # 路径二：go_to(mode="due") 桥接 → 显式到期模式（退出计划模式）
    at.session_state["param_mode"] = "due"
    at.run()
    assert not at.exception
    marks = [str(m.value) for m in at.markdown]
    assert any("道错题待复习" in m for m in marks)
    assert not any("计划模式" in m for m in marks)

    # 路径三：菜单直达（无桥接参数）→ 默认到期队列
    _goto_page(at, "今日复习")
    assert not at.exception
    marks = [str(m.value) for m in at.markdown]
    assert any("道错题待复习" in m for m in marks)
    assert any(b.label == "显示解析" for b in at.button)


def test_review_page_grade_flow_full_rerun(smoke_user, service):
    """菜单直达 → 显示解析（片段重跑同轮渲染评分区）→ 评分（整页 st.rerun()）→
    唯一一题评完队列为空，进入完成态。"""
    _seed_question(
        service, smoke_user.id, "评分链路冒烟题：一元二次方程求根", "x = 2", "复习冒烟"
    )
    at = AppTest.from_file(_APP_ENTRY, default_timeout=180)
    at.run()
    _fill_and_login(at, smoke_user.username, _SMOKE_PASSWORD)
    _goto_page(at, "今日复习")
    assert not at.exception

    reveal = [b for b in at.button if b.label == "显示解析"]
    assert reveal, "到期队列为空（应先经 create_manual_question 建题），断言空转"
    reveal[0].click()
    at.run()
    assert not at.exception
    # 解析与评分按钮同轮渲染（「显示解析」置 key）
    assert any(b.label == "😎 秒懂" for b in at.button)
    assert any("答案" in str(m.value) for m in at.markdown)

    grade = [b for b in at.button if b.label == "😎 秒懂"][0]
    grade.click()
    at.run()
    assert not at.exception
    # 评分保留整页 st.rerun()：队列弹出唯一一题 → 完成态（侧边栏徽标随之准确）
    assert any("本轮复习完成" in str(s.value) for s in at.success)
