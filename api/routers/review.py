"""复习路由：到期错题 / 评分调度 / 追问对话。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from api.deps import get_current_user
from backend.models.orm import User
from backend.models.schemas import KPMasteryOut, QuestionOut, ReviewPlanItemOut
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


@router.get("/history")
def review_history(
    limit: int = 20, user: User = Depends(get_current_user)
) -> list[dict]:
    """最近的复习记录（新→旧）。"""
    from backend.services.question_service import QuestionService

    return QuestionService().recent_reviews(user.id, limit=limit)


@router.get("/due", response_model=list[QuestionOut])
def due_questions(user: User = Depends(get_current_user)) -> list[QuestionOut]:
    return _service().due_questions(user.id)


@router.get("/mastery", response_model=list[KPMasteryOut])
def mastery_profile(
    limit: int | None = None, user: User = Depends(get_current_user)
) -> list[KPMasteryOut]:
    """知识点掌握度画像，薄弱者排前（Batch 04）。"""
    items = _service().mastery_profile(user.id, limit=limit)
    return [
        KPMasteryOut(
            knowledge_point=item.knowledge_point,
            mastery=round(item.mastery, 4),
            question_count=item.question_count,
            due_count=item.due_count,
            status=item.status,
            status_label=item.status_label,
        )
        for item in items
    ]


@router.get("/today", response_model=list[ReviewPlanItemOut])
def today_plan(
    size: int = 10, user: User = Depends(get_current_user)
) -> list[ReviewPlanItemOut]:
    """今日自适应复习计划：SM-2 到期优先 + 薄弱知识点加固（Batch 05）。"""
    size = max(1, min(size, 50))
    items = _service().today_plan(user.id, size=size)
    return [
        ReviewPlanItemOut(
            question=item.question,
            reason=item.reason,
            priority=round(item.priority, 4),
        )
        for item in items
    ]


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
