"""JWT 令牌签发与校验（供 FastAPI 网关使用）。

双令牌（Batch 10）：短效 access（默认 30 分钟）+ 长效 refresh（默认 7 天），
`POST /api/auth/refresh` 用 refresh 换新 access。
历史令牌无 typ 声明，校验时按 access 处理，保证旧客户端平滑过渡。
"""
from __future__ import annotations

import datetime as dt

import jwt

from backend.config import get_settings
from backend.utils.logging import get_logger

logger = get_logger("token")
_ALGORITHM = "HS256"


class TokenError(Exception):
    """令牌无效或已过期。"""


def _create_token(user_id: int, role: str, token_type: str, minutes: int) -> str:
    settings = get_settings()
    now = dt.datetime.now(dt.timezone.utc)
    payload = {
        "sub": str(user_id),
        "role": role,
        "typ": token_type,
        "iat": now,
        "exp": now + dt.timedelta(minutes=minutes),
    }
    return jwt.encode(payload, settings.auth_secret, algorithm=_ALGORITHM)


def create_access_token(user_id: int, role: str) -> str:
    settings = get_settings()
    return _create_token(user_id, role, "access", settings.access_token_expire_minutes)


def create_refresh_token(user_id: int, role: str) -> str:
    settings = get_settings()
    return _create_token(
        user_id, role, "refresh", settings.refresh_token_expire_days * 24 * 60
    )


def decode_token(token: str, expected_type: str = "access") -> dict:
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.auth_secret, algorithms=[_ALGORITHM])
    except jwt.ExpiredSignatureError as exc:
        raise TokenError("令牌已过期") from exc
    except jwt.InvalidTokenError as exc:
        raise TokenError("令牌无效") from exc
    token_type = payload.get("typ", "access")  # 旧令牌无 typ，视为 access
    if expected_type != "any" and token_type != expected_type:
        raise TokenError(f"令牌类型不符：需要 {expected_type}，实际 {token_type}")
    return payload


def decode_access_token(token: str) -> dict:
    """兼容旧调用名：校验 access 令牌并返回载荷。"""
    return decode_token(token, "access")
