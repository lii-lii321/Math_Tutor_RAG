"""异步任务服务：耗时操作（图片 AI 解析）的队列提交与状态追踪。

单进程内用后台线程执行（与 Streamlit 执行模型兼容）；
表结构与 API 是队列协议，未来可平滑替换为 Celery worker。
"""
from __future__ import annotations

import datetime as dt
import threading
import uuid

from sqlalchemy import select

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
        job_dir = get_settings_data_dir() / "jobs"
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

        thread = threading.Thread(
            target=self._run_analyze, args=(job_id, user_id), daemon=True
        )
        thread.start()
        logger.info("异步解析任务已提交 job=%s user=%s", job_id, user_id)
        return job_id

    def _run_analyze(self, job_id: str, user_id: int) -> None:
        from backend.services.question_service import QuestionService

        with SessionLocal() as session:
            job = session.get(Job, job_id)
            if job is None:
                return
            payload = dict(job.payload or {})
            job.status = "running"
            session.commit()

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
            self._finish(job_id, status="success", result=result)
        except Exception as exc:  # noqa: BLE001 - 失败落库供轮询方查看
            logger.warning("异步解析失败 job=%s: %s", job_id, exc)
            self._finish(job_id, status="failed", error=str(exc))
        finally:
            with suppress_oserror():
                Path(payload.get("image_path", "")).unlink(missing_ok=True)

    def _finish(self, job_id: str, *, status: str, result: dict | None = None, error: str | None = None) -> None:
        with SessionLocal() as session:
            job = session.get(Job, job_id)
            if job is None:
                return
            job.status = status
            job.result = result
            job.error = error
            job.finished_at = dt.datetime.now(dt.timezone.utc)
            session.commit()

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


def get_settings_data_dir():
    from backend.config import get_settings

    return get_settings().data_dir


def suppress_oserror():
    from contextlib import suppress

    return suppress(OSError)


from pathlib import Path  # noqa: E402
