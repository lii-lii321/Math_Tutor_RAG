"""认证服务：登录校验、注册、改密、登录失败限流。统一入口避免散落的密码逻辑。"""
from __future__ import annotations

import time

from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.models.schemas import LoginResult, RegisterInput
from backend.repositories.users import UserRepository
from backend.utils.logging import get_logger
from backend.utils.rate_limit import InMemoryRateLimiter, RateLimiter
from backend.utils.security import verify_password

logger = get_logger("auth")

_FAIL_DELAY_SECONDS = 1.0  # 失败时固定延迟，抑制暴力枚举

# 进程内默认限流器；多实例部署可注入 Redis 实现的 RateLimiter
_login_limiter: RateLimiter = InMemoryRateLimiter()


class AuthService:
    def __init__(self, session: Session, limiter: RateLimiter | None = None):
        self.repo = UserRepository(session)
        self.session = session
        self.limiter = limiter or _login_limiter

    def login(self, username: str, password: str) -> LoginResult:
        key = (username or "").strip().lower()
        if self.limiter.is_locked(key):
            logger.warning("用户名 %s 触发登录限流", key)
            return LoginResult(ok=False, message="尝试次数过多，请 5 分钟后再试")

        user = self.repo.get_by_username(username)
        if user is None or not verify_password(password, user.password_hash):
            self.limiter.record_failure(key)
            time.sleep(_FAIL_DELAY_SECONDS)
            return LoginResult(ok=False, message="用户名或密码错误")

        self.limiter.reset(key)
        logger.info("用户登录成功: %s", user.username)
        return LoginResult(
            ok=True, user_id=user.id, username=user.username, role=user.role
        )

    def register(self, data: RegisterInput) -> LoginResult:
        try:
            user = self.repo.create(data, get_settings().bcrypt_rounds)
        except ValueError as exc:
            return LoginResult(ok=False, message=str(exc))
        return LoginResult(
            ok=True, user_id=user.id, username=user.username, role=user.role
        )

    def change_password(self, user_id: int, old_password: str, new_password: str) -> LoginResult:
        user = self.repo.get_by_id(user_id)
        if user is None or not verify_password(old_password, user.password_hash):
            return LoginResult(ok=False, message="原密码不正确")
        if len(new_password) < 6:
            return LoginResult(ok=False, message="新密码至少 6 位")
        self.repo.update_password(user_id, new_password, get_settings().bcrypt_rounds)
        user.token_version += 1  # 改密即吊销全部旧令牌
        logger.info("用户 %s 改密成功，令牌版本升至 %s", user.username, user.token_version)
        return LoginResult(ok=True, message="密码已更新")

    def bump_token_version(self, user_id: int) -> bool:
        """递增令牌版本，吊销该用户当前全部令牌（登出用）。"""
        user = self.repo.get_by_id(user_id)
        if user is None:
            return False
        user.token_version += 1
        logger.info("用户 %s 登出，令牌版本升至 %s", user.username, user.token_version)
        return True
