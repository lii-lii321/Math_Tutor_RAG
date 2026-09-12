"""标签管理路由：用量统计 / 重命名 / 删除。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.deps import get_current_user
from backend.models.orm import User
from backend.services.question_service import QuestionService

router = APIRouter(prefix="/tags", tags=["tags"])


class RenameRequest(BaseModel):
    old: str
    new: str


class MutateResult(BaseModel):
    updated: int


def _service() -> QuestionService:
    return QuestionService()


@router.get("")
def tag_usage(user: User = Depends(get_current_user)) -> dict:
    """当前用户的标签用量：{标签: 题数}，按题数降序。"""
    return _service().tag_usage(user.id)


@router.post("/rename", response_model=MutateResult)
def rename_tag(
    payload: RenameRequest, user: User = Depends(get_current_user)
) -> MutateResult:
    try:
        updated = _service().rename_tag(user.id, payload.old, payload.new)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return MutateResult(updated=updated)


@router.delete("/{tag}", response_model=MutateResult)
def delete_tag(tag: str, user: User = Depends(get_current_user)) -> MutateResult:
    try:
        updated = _service().delete_tag(user.id, tag)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return MutateResult(updated=updated)
