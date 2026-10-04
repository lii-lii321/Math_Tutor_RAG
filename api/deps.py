"""FastAPI 依赖注入：数据库会话、当前用户、共享服务与端点请求限流。"""
from __future__ import annotations

from collections.abc import Callable, Iterator
from functools import lru_cache

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.database import session_scope
from backend.models.orm import User
from backend.services.question_service import QuestionService
from backend.utils.request_limiter import RequestRateLimiter
from backend.utils.tokens import TokenError, decode_access_token

_bearer = HTTPBearer(auto_error=False)

# 进程内滑窗限流器：单实例足够；多实例部署可替换为 Redis 实现
_limiters: dict[str, RequestRateLimiter] = {}


@lru_cache
def get_question_service() -> QuestionService:
    """进程级共享 QuestionService（无每请求状态，session-per-operation 安全）。"""
    return QuestionService()


def get_rate_limiter(scope: str, per_minute: int) -> RequestRateLimiter:
    """按作用域取限流器（进程级单例，配置变更需重启生效）。

    rate_limit_backend=redis 时走 RedisRequestRateLimiter（多实例共享计数）；
    redis 依赖缺失或连接失败时回退进程内实现并告警，保证限流始终可用。
    """
    if scope not in _limiters:
        settings = get_settings()
        if settings.rate_limit_backend == "redis":
            try:
                from backend.utils.request_limiter import RedisRequestRateLimiter

                _limiters[scope] = RedisRequestRateLimiter(
                    settings.redis_url, max_requests=per_minute, window_seconds=60
                )
                return _limiters[scope]
            except Exception as exc:  # noqa: BLE001 - 限流不可用时降级为进程内
                import logging

                logging.getLogger("uvicorn.error").warning(
                    "Redis 限流后端不可用（%s），scope=%s 回退进程内计数", exc, scope
                )
        _limiters[scope] = RequestRateLimiter(per_minute, window_seconds=60)
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
    # session-per-operation 统一收口（提交/回滚/归还，见 backend/database.py）
    with session_scope() as session:
        yield session


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
    if payload.get("tv", 0) != user.token_version:
        # 改密 / 登出后 token_version 已递增，旧令牌整体吊销
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "令牌已失效，请重新登录")
    return user
