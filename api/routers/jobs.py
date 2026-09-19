"""任务轮询路由：GET /api/jobs/{job_id}。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api.deps import get_current_user
from backend.models.orm import User
from backend.services.job_service import JobService

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("/{job_id}")
def get_job(job_id: str, user: User = Depends(get_current_user)) -> dict:
    job = JobService().get(job_id, user.id)
    if job is None:
        raise HTTPException(404, "任务不存在")
    return job
