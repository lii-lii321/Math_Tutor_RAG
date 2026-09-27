"""任务队列后端抽象：JobQueue Protocol + 线程 / RQ 两个实现。

选择逻辑（get_job_queue）：
- 未配置 REDIS_URL → ThreadedJobQueue（进程内 daemon 线程，单实例默认）
- 配置了 REDIS_URL → RQJobQueue（Redis + 独立 Worker，多实例部署）

rq / redis 为可选依赖：未安装时 RQJobQueue 构造抛 RuntimeError 并回退线程。
"""
from __future__ import annotations

import threading
from typing import Protocol, runtime_checkable

from backend.utils.logging import get_logger

logger = get_logger("jobs")

QUEUE_NAME = "mathmaster"


@runtime_checkable
class JobQueue(Protocol):
    def submit_analyze(self, job_id: str, user_id: int) -> None:
        """把已入库的任务投入执行（不阻塞调用方）。"""
        ...


class ThreadedJobQueue:
    """进程内线程后端：与 Streamlit 执行模型兼容，零外部依赖。"""

    def submit_analyze(self, job_id: str, user_id: int) -> None:
        from backend.jobs.tasks import run_analyze_job

        thread = threading.Thread(
            target=run_analyze_job, args=(job_id, user_id), daemon=True
        )
        thread.start()


class RQJobQueue:
    """RQ（Redis Queue）后端：任务进入 Redis，由独立 Worker 进程消费。"""

    def __init__(self, redis_url: str, queue_name: str = QUEUE_NAME):
        try:
            from redis import Redis
            from rq import Queue
        except ImportError as exc:  # 可选依赖缺失时明确报错
            raise RuntimeError(
                "REDIS_URL 已配置但 rq/redis 未安装：pip install -r requirements-queue.txt"
            ) from exc
        self._connection = Redis.from_url(redis_url)
        self._queue: Queue = Queue(queue_name, connection=self._connection)

    def submit_analyze(self, job_id: str, user_id: int) -> None:
        from backend.jobs.tasks import run_analyze_job

        rq_job = self._queue.enqueue(run_analyze_job, job_id, user_id)
        logger.info("任务已入 RQ 队列 job=%s rq_job=%s", job_id, rq_job.id)


def get_job_queue(redis_url: str | None = None) -> JobQueue:
    """按配置返回队列后端；RQ 不可用时告警并回退线程（保证任务仍可执行）。"""
    if not redis_url:
        return ThreadedJobQueue()
    try:
        return RQJobQueue(redis_url)
    except RuntimeError as exc:
        logger.warning("%s；回退为线程执行", exc)
        return ThreadedJobQueue()
