"""统计路由：看板数据 / 标签共现图谱。"""
from __future__ import annotations

from collections import Counter
from itertools import combinations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.deps import get_current_user
from backend.models.orm import User
from backend.services.question_service import QuestionService

router = APIRouter(prefix="/stats", tags=["stats"])


class CooccurrenceEdge(BaseModel):
    source: str
    target: str
    weight: int


def _service() -> QuestionService:
    return QuestionService()


@router.get("/dashboard")
def dashboard(user: User = Depends(get_current_user)) -> dict:
    """学情看板数据：总数 / 到期 / 标签掌握度 / 活跃度。"""
    return _service().dashboard_stats(user.id, include_others=user.role == "teacher")


@router.get("/tag-graph", response_model=list[CooccurrenceEdge])
def tag_graph(user: User = Depends(get_current_user)) -> list[CooccurrenceEdge]:
    """标签共现边列表：节点=标签，边=两标签同时出现在一道错题中。"""
    questions = _service().list_questions(user.id, semantic=False)
    edges: Counter[tuple[str, str]] = Counter()
    for question in questions:
        tags = sorted(set(question.tags or []))
        for a, b in combinations(tags, 2):
            edges[(a, b)] += 1
    return [
        CooccurrenceEdge(source=a, target=b, weight=count)
        for (a, b), count in edges.most_common()
    ]
