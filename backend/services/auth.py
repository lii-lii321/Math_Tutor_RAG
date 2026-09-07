"""认证服务：登录校验、注册、改密。统一入口避免散落的密码逻辑。"""
from __future__ import annotations

import time

from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.models.schemas import LoginResult, RegisterInput
from backend.repositories.users import UserRepository
from backend.utils.logging import get_logger
from backend.utils.security import verify_password

logger = get_logger("auth")

_FAIL_DELAY_SECONDS = 1.0  # 失败时固定延迟，抑制暴力枚举


class AuthService:
    def __init__(self, session: Session):
        self.repo = UserRepository(session)
        self.session = session

    def login(self, username: str, password: str) -> LoginResult:
        user = self.repo.get_by_username(username)
        if user is None or not verify_password(password, user.password_hash):
            time.sleep(_FAIL_DELAY_SECONDS)
            return LoginResult(ok=False, message="用户名或密码错误")
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
