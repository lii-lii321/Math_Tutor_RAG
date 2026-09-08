"""JWT 令牌签发与校验（供 FastAPI 网关使用）。"""
from __future__ import annotations

import datetime as dt

import jwt

from backend.config import get_settings
from backend.utils.logging import get_logger

logger = get_logger("token")
_ALGORITHM = "HS256"


class TokenError(Exception):
    """令牌无效或已过期。"""


def create_access_token(user_id: int, role: str) -> str:
    settings = get_settings()
    now = dt.datetime.now(dt.timezone.utc)
    payload = {
        "sub": str(user_id),
        "role": role,
        "iat": now,
        "exp": now + dt.timedelta(minutes=settings.access_token_expire_minutes),
    }
    return jwt.encode(payload, settings.auth_secret, algorithm=_ALGORITHM)


def decode_access_token(token: str) -> dict:
    settings = get_settings()
    try:
        return jwt.decode(token, settings.auth_secret, algorithms=[_ALGORITHM])
    except jwt.ExpiredSignatureError as exc:
        raise TokenError("令牌已过期") from exc
    except jwt.InvalidTokenError as exc:
        raise TokenError("令牌无效") from exc
