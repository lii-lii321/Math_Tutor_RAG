"""认证服务：登录校验、注册、改密、登录失败限流。统一入口避免散落的密码逻辑。"""
from __future__ import annotations

import time
from collections import defaultdict

from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.models.schemas import LoginResult, RegisterInput
from backend.repositories.users import UserRepository
from backend.utils.logging import get_logger
from backend.utils.security import verify_password

logger = get_logger("auth")

_FAIL_DELAY_SECONDS = 1.0  # 失败时固定延迟，抑制暴力枚举


class LoginRateLimiter:
    """内存级登录失败限流：同一用户名在时间窗口内失败超限后临时锁定。

    适用于单进程部署（Streamlit / 单 uvicorn 实例）；多实例部署应改用
    Redis 等共享存储。锁定阈值与窗口由实例参数决定。
    """

    def __init__(self, max_failures: int = 5, window_seconds: int = 300):
        self.max_failures = max_failures
        self.window_seconds = window_seconds
        self._failures: dict[str, list[float]] = defaultdict(list)

    def is_locked(self, key: str) -> bool:
        now = time.monotonic()
        recent = [t for t in self._failures[key] if now - t < self.window_seconds]
        self._failures[key] = recent
        return len(recent) >= self.max_failures

    def record_failure(self, key: str) -> None:
        self._failures[key].append(time.monotonic())

    def reset(self, key: str) -> None:
        self._failures.pop(key, None)


_login_limiter = LoginRateLimiter()


class AuthService:
    def __init__(self, session: Session):
        self.repo = UserRepository(session)
        self.session = session

    def login(self, username: str, password: str) -> LoginResult:
        key = (username or "").strip().lower()
        if _login_limiter.is_locked(key):
            logger.warning("用户名 %s 触发登录限流", key)
            return LoginResult(ok=False, message="尝试次数过多，请 5 分钟后再试")

        user = self.repo.get_by_username(username)
        if user is None or not verify_password(password, user.password_hash):
            _login_limiter.record_failure(key)
            time.sleep(_FAIL_DELAY_SECONDS)
            return LoginResult(ok=False, message="用户名或密码错误")

        _login_limiter.reset(key)
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
        return LoginResult(ok=True, message="密码已更新")
