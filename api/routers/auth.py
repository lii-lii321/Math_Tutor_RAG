"""认证路由：登录 / 注册 / 刷新令牌 / 登出，返回 JWT。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from api.deps import get_current_user, get_db
from backend.models.orm import User
from backend.models.schemas import RegisterInput
from backend.services.auth import AuthService
from backend.utils.tokens import (
    TokenError,
    create_access_token,
    create_refresh_token,
    decode_token,
)

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=64)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=10)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user_id: int
    username: str
    role: str


def _token_pair(user: User) -> TokenResponse:
    from backend.config import get_settings

    return TokenResponse(
        access_token=create_access_token(user.id, user.role, user.token_version),
        refresh_token=create_refresh_token(user.id, user.role, user.token_version),
        expires_in=get_settings().access_token_expire_minutes * 60,
        user_id=user.id,
        username=user.username,
        role=user.role,
    )


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    result = AuthService(db).login(payload.username, payload.password)
    if not result.ok:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, result.message or "登录失败")
    assert result.user_id is not None
    user = db.get(User, result.user_id)
    assert user is not None
    return _token_pair(user)


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterInput, db: Session = Depends(get_db)) -> TokenResponse:
    result = AuthService(db).register(payload)
    if not result.ok:
        raise HTTPException(status.HTTP_409_CONFLICT, result.message or "注册失败")
    assert result.user_id is not None
    user = db.get(User, result.user_id)
    assert user is not None
    return _token_pair(user)


@router.post("/refresh", response_model=TokenResponse)
def refresh(payload: RefreshRequest, db: Session = Depends(get_db)) -> TokenResponse:
    """用长效 refresh 换新令牌对（rotation-lite：refresh 同步轮换）。"""
    try:
        claims = decode_token(payload.refresh_token, expected_type="refresh")
    except TokenError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc
    user_id = int(claims["sub"])
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "用户不存在")
    if claims.get("tv", 0) != user.token_version:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "令牌已失效，请重新登录")
    return _token_pair(user)


@router.post("/logout")
def logout(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> dict:
    """登出：递增 token_version，吊销该用户当前签发的全部令牌。"""
    AuthService(db).bump_token_version(user.id)
    return {"ok": True}
