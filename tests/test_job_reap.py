"""reap_stuck_jobs 超时判定测试（提升项 #16）。

按 COALESCE(started_at, created_at) 判定：长排队（created 早、started 晚）
不误杀；领取后真超时才回收；历史行无 started_at 回退旧行为。
"""
from __future__ import annotations

import datetime as dt
import uuid

from backend.database import SessionLocal
from backend.models.orm import Job
from backend.services.job_service import JobService


def _seed_job(*, status: str, started_at, created_at) -> str:
    job_id = uuid.uuid4().hex
    with SessionLocal() as session:
        session.add(
            Job(
                id=job_id,
                user_id=1,
                type="analyze_image",
                status=status,
                payload={},
                created_at=created_at,
                started_at=started_at,
            )
        )
        session.commit()
    return job_id


def test_long_queued_job_not_reaped():
    """created 90 分钟前、10 分钟前才领取：不回收（旧逻辑会误杀）。"""
    now = dt.datetime.now(dt.timezone.utc)
    job_id = _seed_job(
        status="running",
        started_at=now - dt.timedelta(minutes=10),
        created_at=now - dt.timedelta(minutes=90),
    )
    assert JobService.reap_stuck_jobs(timeout_minutes=30) >= 0
    with SessionLocal() as session:
        job = session.get(Job, job_id)
        assert job.status == "running"


def test_truly_stuck_job_reaped_by_started_at():
    """领取 60 分钟仍 running：回收。"""
    now = dt.datetime.now(dt.timezone.utc)
    job_id = _seed_job(
        status="running",
        started_at=now - dt.timedelta(minutes=60),
        created_at=now - dt.timedelta(minutes=90),
    )
    reaped = JobService.reap_stuck_jobs(timeout_minutes=30)
    assert reaped >= 1
    with SessionLocal() as session:
        job = session.get(Job, job_id)
        assert job.status == "failed"
        assert "进程重启" in (job.error or "")


def test_legacy_row_without_started_at_falls_back_to_created_at():
    """历史行（无 started_at）：按 created_at 判定，与旧行为一致。"""
    now = dt.datetime.now(dt.timezone.utc)
    old = _seed_job(
        status="running",
        started_at=None,
        created_at=now - dt.timedelta(minutes=90),
    )
    recent = _seed_job(
        status="running",
        started_at=None,
        created_at=now - dt.timedelta(minutes=5),
    )
    JobService.reap_stuck_jobs(timeout_minutes=30)
    with SessionLocal() as session:
        assert session.get(Job, old).status == "failed"
        assert session.get(Job, recent).status == "running"
