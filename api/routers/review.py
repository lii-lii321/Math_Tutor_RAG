"""复习路由：到期错题 / 评分调度 / 追问对话。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from api.deps import get_current_user
from backend.models.orm import User
from backend.models.schemas import QuestionOut
from backend.services.question_service import QuestionService
from backend.services.review import GRADE_ORDER

router = APIRouter(prefix="/review", tags=["review"])


class GradeRequest(BaseModel):
    grade: str = Field(description=f"one of {GRADE_ORDER}")


class FollowupRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    history: list[dict] = Field(default_factory=list, max_length=40)


class FollowupResponse(BaseModel):
    reply: str


def _service() -> QuestionService:
    return QuestionService()


@router.get("/due", response_model=list[QuestionOut])
def due_questions(user: User = Depends(get_current_user)) -> list[QuestionOut]:
    return _service().due_questions(user.id)


@router.post("/{question_id}/grade", response_model=QuestionOut)
def grade_question(
    question_id: int, payload: GradeRequest, user: User = Depends(get_current_user)
) -> QuestionOut:
    if payload.grade not in GRADE_ORDER:
        raise HTTPException(422, f"grade 必须是 {GRADE_ORDER} 之一")
    updated = _service().grade_review(question_id, user.id, payload.grade)
    if updated is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "错题不存在")
    return updated


@router.post("/{question_id}/followup", response_model=FollowupResponse)
def followup(
    question_id: int, payload: FollowupRequest, user: User = Depends(get_current_user)
) -> FollowupResponse:
    try:
        reply = _service().answer_followup(
            question_id, user.id, payload.history, payload.question
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return FollowupResponse(reply=reply)
