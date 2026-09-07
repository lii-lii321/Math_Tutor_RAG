"""用户仓储：账号读写与认证查询。"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.orm import User
from backend.models.schemas import RegisterInput
from backend.utils.security import hash_password


class UserRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_by_username(self, username: str) -> User | None:
        return self.session.execute(
            select(User).where(User.username == username.strip())
        ).scalar_one_or_none()

    def get_by_id(self, user_id: int) -> User | None:
        return self.session.get(User, user_id)

    def create(self, data: RegisterInput, bcrypt_rounds: int = 12) -> User:
        if self.get_by_username(data.username) is not None:
            raise ValueError(f"用户名已被占用: {data.username}")
        user = User(
            username=data.username,
            password_hash=hash_password(data.password, bcrypt_rounds),
            role=data.role,
        )
        self.session.add(user)
        self.session.flush()
        return user

    def update_password(self, user_id: int, new_password: str, bcrypt_rounds: int = 12) -> bool:
        user = self.get_by_id(user_id)
        if user is None:
            return False
        user.password_hash = hash_password(new_password, bcrypt_rounds)
        return True
