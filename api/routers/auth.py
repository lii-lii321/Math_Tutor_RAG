"""认证路由：登录 / 注册，返回 JWT。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from api.deps import get_db
from backend.models.schemas import RegisterInput
from backend.services.auth import AuthService
from backend.utils.tokens import create_access_token

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=64)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: int
    username: str
    role: str


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    result = AuthService(db).login(payload.username, payload.password)
    if not result.ok:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, result.message or "登录失败")
    assert result.user_id is not None and result.username is not None and result.role is not None
    return TokenResponse(
        access_token=create_access_token(result.user_id, result.role),
        user_id=result.user_id,
        username=result.username,
        role=result.role,
    )


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterInput, db: Session = Depends(get_db)) -> TokenResponse:
    result = AuthService(db).register(payload)
    if not result.ok:
        raise HTTPException(status.HTTP_409_CONFLICT, result.message or "注册失败")
    assert result.user_id is not None and result.username is not None and result.role is not None
    return TokenResponse(
        access_token=create_access_token(result.user_id, result.role),
        user_id=result.user_id,
        username=result.username,
        role=result.role,
    )
