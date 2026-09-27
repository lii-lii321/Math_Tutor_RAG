"""任务函数：必须保持模块级可导入——Worker 进程按点分路径调用。

执行逻辑与 Threaded/RQ 后端解耦：两种后端跑的是同一份代码。
"""
from __future__ import annotations

import datetime as dt
from contextlib import suppress
from pathlib import Path

from sqlalchemy import select

from backend.database import SessionLocal
from backend.models.orm import Job
from backend.utils.logging import get_logger

logger = get_logger("jobs")

TERMINAL_STATUSES = {"success", "failed", "cancelled"}


def _load_payload(job_id: str) -> tuple[dict, int] | None:
    """读取任务并把状态推进到 running；不存在或已取消返回 None（Worker 跳过）。"""
    with SessionLocal() as session:
        job = session.execute(select(Job).where(Job.id == job_id)).scalar_one_or_none()
        if job is None:
            return None
        if job.status == "cancelled":
            logger.info("任务已被取消，跳过执行 job=%s", job_id)
            return None
        payload = dict(job.payload or {})
        job.status = "running"
        session.commit()
        user_id = job.user_id
    return payload, user_id


def _finish(
    job_id: str, *, status: str, result: dict | None = None, error: str | None = None
) -> None:
    with SessionLocal() as session:
        job = session.get(Job, job_id)
        if job is None:
            return
        job.status = status
        job.result = result
        job.error = error
        job.finished_at = dt.datetime.now(dt.timezone.utc)
        session.commit()


def run_analyze_job(job_id: str, user_id: int) -> None:
    """执行图片 AI 解析任务（与 JobService 旧线程逻辑一致，双后端共用）。"""
    from backend.services.question_service import QuestionService

    loaded = _load_payload(job_id)
    if loaded is None:
        return
    payload, user_id = loaded

    try:
        service = QuestionService(session_factory=SessionLocal)
        image_bytes = Path(payload["image_path"]).read_bytes()
        entry = service.analyze_and_save_dedup(
            user_id,
            image_bytes,
            mime_type=payload.get("mime_type", "image/jpeg"),
            user_tags=list(payload.get("tags") or []),
            hint=payload.get("hint", ""),
        )
        result = {
            "question_id": entry.question.id,
            "duplicated": entry.duplicated,
            "tags": entry.question.tags,
            "answer": entry.question.answer,
        }
        _finish(job_id, status="success", result=result)
    except Exception as exc:  # noqa: BLE001 - 失败落库供轮询方查看
        logger.warning("异步解析失败 job=%s: %s", job_id, exc)
        _finish(job_id, status="failed", error=str(exc))
    finally:
        with suppress(OSError):
            Path(payload.get("image_path", "")).unlink(missing_ok=True)
