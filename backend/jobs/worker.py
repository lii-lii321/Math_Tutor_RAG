"""RQ Worker 入口：消费 mathmaster 队列（Batch 08 生产部署用）。

启动：
    python -m backend.jobs.worker

读取 REDIS_URL 配置（默认 redis://localhost:6379/0）。
与 Web 进程共享同一份 backend 代码与数据库配置。
"""
from __future__ import annotations

from backend.config import get_settings
from backend.utils.logging import get_logger

logger = get_logger("jobs")

QUEUE_NAME = "mathmaster"


def main() -> None:
    from redis import Redis
    from rq import Worker

    settings = get_settings()
    redis_url = settings.redis_url or "redis://localhost:6379/0"
    connection = Redis.from_url(redis_url)
    worker = Worker([QUEUE_NAME], connection=connection, name=f"mathmaster-worker-{QUEUE_NAME}")
    logger.info("RQ Worker 启动 queue=%s redis=%s", QUEUE_NAME, redis_url)
    worker.work()


if __name__ == "__main__":
    main()
