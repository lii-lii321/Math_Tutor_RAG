"""FastAPI 依赖注入：数据库会话、当前用户与端点请求限流。"""
from __future__ import annotations

from collections.abc import Callable, Iterator

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.database import SessionLocal
from backend.models.orm import User
from backend.utils.request_limiter import RequestRateLimiter
from backend.utils.tokens import TokenError, decode_access_token

_bearer = HTTPBearer(auto_error=False)

# 进程内滑窗限流器：单实例足够；多实例部署可替换为 Redis 实现
_limiters: dict[str, RequestRateLimiter] = {}


def get_rate_limiter(scope: str, per_minute: int) -> RequestRateLimiter:
    """按作用域取限流器（进程级单例，配置变更需重启生效）。"""
    if scope not in _limiters:
        _limiters[scope] = RequestRateLimiter(
            per_minute, window_seconds=60
        )
    return _limiters[scope]


def rate_limit(scope: str) -> Callable[..., None]:
    """端点依赖工厂：按「scope:用户」做每分钟配额（配置为 0 时放行）。"""

    def dependency(user: User = Depends(get_current_user)) -> None:
        per_minute = getattr(get_settings(), f"rate_limit_{scope}_per_min", 0)
        if per_minute <= 0:
            return
        if not get_rate_limiter(scope, per_minute).allow(f"{scope}:{user.id}"):
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS, "请求过于频繁，请稍后再试"
            )

    return dependency


def get_db() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "缺少认证令牌")
    try:
        payload = decode_access_token(credentials.credentials)
    except TokenError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc
    user = db.get(User, int(payload["sub"]))
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "用户不存在")
    return user
