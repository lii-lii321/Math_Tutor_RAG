"""批注路由：错题下的教师批注 / 用户留言。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.deps import get_current_user
from backend.models.orm import User
from backend.services.comment_service import CommentService, QuestionAccessDenied

router = APIRouter(prefix="/questions/{question_id}/comments", tags=["comments"])


class CommentInput(BaseModel):
    content: str = Field(min_length=1, max_length=2000)


def _service() -> CommentService:
    return CommentService()


@router.get("")
def list_comments(question_id: int, user: User = Depends(get_current_user)) -> list[dict]:
    try:
        return _service().list_for_question(
            question_id, viewer_id=user.id, viewer_role=user.role
        )
    except QuestionAccessDenied as exc:
        # 不存在与无权访问统一 404，不泄露存在性
        raise HTTPException(404, "错题不存在") from exc


@router.post("", status_code=201)
def add_comment(
    question_id: int,
    payload: CommentInput,
    user: User = Depends(get_current_user),
) -> dict:
    try:
        return _service().add(question_id, user.id, payload.content, viewer_role=user.role)
    except QuestionAccessDenied as exc:
        raise HTTPException(404, "错题不存在") from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.delete("/{comment_id}", status_code=204)
def delete_comment(
    question_id: int,
    comment_id: int,
    user: User = Depends(get_current_user),
) -> None:
    deleted = _service().delete(comment_id, user.id, is_teacher=user.role == "teacher")
    if not deleted:
        raise HTTPException(404, "批注不存在或无权删除")
