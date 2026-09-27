"""统计路由：看板数据 / 标签共现图谱。"""
from __future__ import annotations

from collections import Counter
from itertools import combinations

from fastapi import APIRouter, Depends, HTTPException
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


@router.get("/students")
def students_overview(user: User = Depends(get_current_user)) -> list[dict]:
    """教师专属：全班学生错题/复习/掌握度汇总。"""
    try:
        return _service().students_overview(user.id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


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


@router.get("/observability")
def observability(
    limit: int = 200, user: User = Depends(get_current_user)
) -> dict:
    """运行观测摘要（手册 §十一）：AI 延迟/错误率 + 异步任务失败率。

    遥测来自本地 JSONL（data/telemetry/ai_calls.jsonl），
    任务失败率取最近 limit 条 jobs 记录。
    """
    from sqlalchemy import func, select

    from backend.database import SessionLocal
    from backend.models.orm import Job
    from backend.services.ai.telemetry import summarize

    summary = summarize(limit=min(limit, 1000))
    with SessionLocal() as session:
        total_jobs = (
            session.execute(select(func.count()).select_from(Job)).scalar_one()
        )
        failed_jobs = (
            session.execute(
                select(func.count())
                .select_from(Job)
                .where(Job.status == "failed")
            )
            .scalar_one()
        )
    return {
        "ai": summary,
        "jobs": {
            "total": total_jobs,
            "failed": failed_jobs,
            "failure_rate": round(failed_jobs / total_jobs * 100, 1) if total_jobs else None,
        },
    }
