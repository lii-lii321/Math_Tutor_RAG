"""登录失败限流测试。"""
from __future__ import annotations

import pytest

from backend.services.auth import AuthService, LoginRateLimiter


@pytest.fixture
def limiter():
    return LoginRateLimiter(max_failures=3, window_seconds=60)


def test_rate_limiter_locks_after_failures(limiter):
    key = "user1"
    assert not limiter.is_locked(key)
    for _ in range(3):
        limiter.record_failure(key)
    assert limiter.is_locked(key)
    assert not limiter.is_locked("user2")  # 不同用户名互不影响


def test_rate_limiter_resets_on_success(limiter):
    key = "user1"
    for _ in range(3):
        limiter.record_failure(key)
    limiter.reset(key)
    assert not limiter.is_locked(key)


def test_login_locked_returns_friendly_message(db_session, monkeypatch):
    from backend.services import auth as auth_module

    monkeypatch.setattr(
        auth_module, "_login_limiter", LoginRateLimiter(max_failures=1, window_seconds=60)
    )
    service = AuthService(db_session)

    first = service.login("demo", "wrong-password")
    assert not first.ok and first.message == "用户名或密码错误"

    locked = service.login("demo", "demo123")  # 即使密码正确也应被限流
    assert not locked.ok and "尝试次数过多" in locked.message


def test_login_success_after_failures_clears_limit(db_session, monkeypatch):
    from backend.services import auth as auth_module

    monkeypatch.setattr(
        auth_module, "_login_limiter", LoginRateLimiter(max_failures=5, window_seconds=60)
    )
    service = AuthService(db_session)
    service.login("demo", "wrong")  # 留下失败记录
    ok = service.login("demo", "demo123")
    assert ok.ok

    # 成功后限流计数已清零，再次失败不会立刻锁死
    again = service.login("demo", "wrong")
    assert again.ok is False and again.message == "用户名或密码错误"
