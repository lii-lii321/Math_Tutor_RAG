"""登录失败限流测试（InMemoryRateLimiter + AuthService 集成）。"""
from __future__ import annotations

import pytest

from backend.services.auth import AuthService
from backend.utils.rate_limit import InMemoryRateLimiter, RateLimiter


@pytest.fixture
def limiter():
    return InMemoryRateLimiter(max_failures=3, window_seconds=60)


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


def test_rate_limiter_satisfies_protocol(limiter):
    assert isinstance(limiter, RateLimiter)


def _fresh_service(db_session, max_failures: int = 5) -> AuthService:
    return AuthService(db_session, limiter=InMemoryRateLimiter(max_failures=max_failures))


def test_login_locked_returns_friendly_message(db_session):
    service = _fresh_service(db_session, max_failures=1)

    first = service.login("demo", "wrong-password")
    assert not first.ok and first.message == "用户名或密码错误"

    locked = service.login("demo", "demo123")  # 即使密码正确也应被限流
    assert not locked.ok and "尝试次数过多" in locked.message


def test_login_success_after_failures_clears_limit(db_session):
    service = _fresh_service(db_session)
    service.login("demo", "wrong")  # 留下失败记录
    ok = service.login("demo", "demo123")
    assert ok.ok

    # 成功后限流计数已清零，再次失败不会立刻锁死
    again = service.login("demo", "wrong")
    assert again.ok is False and again.message == "用户名或密码错误"


def test_register_and_change_password_still_work(db_session):
    from backend.models.schemas import RegisterInput

    service = _fresh_service(db_session)
    result = service.register(RegisterInput(username="rl_user", password="secret1"))
    assert result.ok
    assert service.change_password(result.user_id, "secret1", "secret2").ok
