"""任务队列后端抽象：JobQueue Protocol + 线程 / RQ / RabbitMQ 三个实现。

选择逻辑（get_job_queue，按优先级）：
- 配置了 RABBITMQ_URL → RabbitMQJobQueue（AMQP 持久化队列 + 独立 Worker）
- 配置了 REDIS_URL → RQJobQueue（Redis + 独立 Worker，多实例部署）
- 都未配置 → ThreadedJobQueue（进程内 daemon 线程，单实例默认）

rq/redis/pika 均为可选依赖：对应后端缺依赖时抛 RuntimeError 并回退线程，
保证任务仍可执行（与降级哲学一致）。
"""
from __future__ import annotations

import json
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


class RabbitMQJobQueue:
    """RabbitMQ（AMQP 0-9-1）后端：任务 JSON 进持久化队列，独立 Worker 消费。

    连接按需建立并复用；发布失败（连接失效等）重连一次重投——任务状态
    以 jobs 表为唯一事实源，极端情况下的重复投递由 Worker 侧 jobs 表
    状态校验（_load_payload 对已取消/已完成任务的语义）与幂等去重兜底。
    """

    def __init__(self, url: str, queue_name: str = QUEUE_NAME):
        try:
            import pika
        except ImportError as exc:  # 可选依赖缺失时明确报错
            raise RuntimeError(
                "RABBITMQ_URL 已配置但 pika 未安装：pip install -r requirements-queue.txt"
            ) from exc
        self._pika = pika
        self._url = url
        self._queue_name = queue_name
        self._connection = None
        self._channel = None

    def _ensure_channel(self):
        if self._connection is None or self._connection.is_closed:
            self._connection = self._pika.BlockingConnection(
                self._pika.URLParameters(self._url)
            )
            self._channel = self._connection.channel()
            self._channel.queue_declare(queue=self._queue_name, durable=True)
        return self._channel

    def _publish(self, channel, job_id: str, user_id: int) -> None:
        channel.basic_publish(
            exchange="",
            routing_key=self._queue_name,
            body=json.dumps({"job_id": job_id, "user_id": user_id}).encode("utf-8"),
            properties=self._pika.BasicProperties(
                delivery_mode=2,  # persistent
                content_type="application/json",
            ),
        )

    def submit_analyze(self, job_id: str, user_id: int) -> None:
        channel = self._ensure_channel()
        try:
            self._publish(channel, job_id, user_id)
        except Exception:  # noqa: BLE001 - 连接失效等：重连一次重投
            logger.warning("RabbitMQ 发布失败，重连重投 job=%s", job_id)
            self._connection = None
            self._publish(self._ensure_channel(), job_id, user_id)
        logger.info("任务已入 RabbitMQ 队列 job=%s queue=%s", job_id, self._queue_name)


def get_job_queue(
    redis_url: str | None = None, rabbitmq_url: str | None = None
) -> JobQueue:
    """按配置返回队列后端；配置了外部队列但依赖不可用时告警并逐级回退线程。"""
    if rabbitmq_url:
        try:
            return RabbitMQJobQueue(rabbitmq_url)
        except RuntimeError as exc:
            logger.warning("%s；尝试 RQ 后端", exc)
    if redis_url:
        try:
            return RQJobQueue(redis_url)
        except RuntimeError as exc:
            logger.warning("%s；回退为线程执行", exc)
    return ThreadedJobQueue()
