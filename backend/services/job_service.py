"""异步任务服务：耗时操作（图片 AI 解析）的队列提交、取消与状态追踪。

执行后端由配置决定（Batch 08）：
- 未配置 REDIS_URL：进程内 daemon 线程（单实例默认）
- 配置 REDIS_URL：RQ 队列 + 独立 Worker（python -m backend.jobs.worker）

jobs 表是唯一状态源：pending → running → success / failed / cancelled。
"""
from __future__ import annotations

import datetime as dt
import uuid
from contextlib import suppress
from pathlib import Path

from sqlalchemy import select

from backend.config import get_settings
from backend.database import SessionLocal
from backend.models.orm import Job
from backend.utils.logging import get_logger

logger = get_logger("jobs")


class JobService:
    def submit_analyze(
        self,
        user_id: int,
        image_bytes: bytes,
        *,
        filename: str,
        mime_type: str,
        tags: list[str] | None = None,
        hint: str = "",
    ) -> str:
        """创建异步解析任务并立即返回 job_id（图片存入任务目录等待执行）。"""
        job_id = uuid.uuid4().hex
        job_dir = get_settings().data_dir / "jobs"
        job_dir.mkdir(parents=True, exist_ok=True)
        image_path = job_dir / f"{job_id}.jpg"
        image_path.write_bytes(image_bytes)

        with SessionLocal() as session:
            session.add(
                Job(
                    id=job_id,
                    user_id=user_id,
                    type="analyze_image",
                    status="pending",
                    payload={
                        "filename": filename,
                        "mime_type": mime_type,
                        "image_path": str(image_path),
                        "tags": tags or [],
                        "hint": hint,
                    },
                )
            )
            session.commit()

        self._queue().submit_analyze(job_id, user_id)
        logger.info("异步解析任务已提交 job=%s user=%s", job_id, user_id)
        return job_id

    @staticmethod
    def _queue():
        """按当前配置取队列后端（每次提交时解析，配置热切换即生效）。"""
        from backend.jobs.queue import get_job_queue

        return get_job_queue(get_settings().redis_url)

    def cancel(self, job_id: str, user_id: int) -> bool:
        """取消任务：仅 pending 状态可取消；执行中/已结束返回 False。"""
        with SessionLocal() as session:
            job = session.execute(
                select(Job).where(Job.id == job_id, Job.user_id == user_id)
            ).scalar_one_or_none()
            if job is None or job.status != "pending":
                return False
            job.status = "cancelled"
            job.finished_at = dt.datetime.now(dt.timezone.utc)
            session.commit()
            payload_image = dict(job.payload or {}).get("image_path", "")
        # Worker 取任务时会二次校验状态，双重保证取消语义
        logger.info("任务已取消 job=%s user=%s", job_id, user_id)
        with suppress(OSError):
            Path(payload_image).unlink(missing_ok=True)
        return True

    def get(self, job_id: str, user_id: int) -> dict | None:
        """查询任务状态（按用户隔离）。"""
        with SessionLocal() as session:
            job = session.execute(
                select(Job).where(Job.id == job_id, Job.user_id == user_id)
            ).scalar_one_or_none()
            if job is None:
                return None
            return {
                "job_id": job.id,
                "status": job.status,
                "type": job.type,
                "result": job.result,
                "error": job.error,
                "created_at": job.created_at,
                "finished_at": job.finished_at,
            }
