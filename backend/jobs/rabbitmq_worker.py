"""RabbitMQ Worker：消费 mathmaster 队列，执行异步解析任务。

启动：python -m backend.jobs.rabbitmq_worker（RABBITMQ_URL 需已配置）

语义约定：
- 消息体 JSON {"job_id", "user_id"}，持久化投递（delivery_mode=2）；
- prefetch=1 + 逐条 ack：单 Worker 串行消费，避免 AI 解析并发打爆配额；
- **无论任务执行成败都 ack**：run_analyze_job 内部已把成败写入 jobs 表
  （唯一状态源），requeue 只会重复执行昂贵的 AI 调用；
- 队列声明为 durable，与发布端（RabbitMQJobQueue）一致，Broker 重启不丢任务。
"""
from __future__ import annotations

import json
import os
import sys

from backend.utils.logging import get_logger

logger = get_logger("jobs")

PREFETCH_COUNT = 1


def handle_message(body: bytes) -> None:
    """解析消息并执行任务（与队列接线分离，便于脱机单测）。"""
    from backend.jobs.tasks import run_analyze_job

    payload = json.loads(body.decode("utf-8"))
    run_analyze_job(payload["job_id"], payload["user_id"])


def consume(url: str, queue_name: str = "mathmaster") -> None:  # noqa: B008 - 与 QUEUE_NAME 同源默认
    import pika

    connection = pika.BlockingConnection(pika.URLParameters(url))
    channel = connection.channel()
    channel.queue_declare(queue=queue_name, durable=True)
    channel.basic_qos(prefetch_count=PREFETCH_COUNT)

    def _on_message(ch, method, properties, body):  # noqa: ANN001 - pika 回调签名
        try:
            handle_message(body)
        except Exception:  # noqa: BLE001 - 解析失败等异常不中断消费循环
            logger.exception("RabbitMQ 消息处理失败（已 ack，任务状态见 jobs 表）")
        finally:
            ch.basic_ack(delivery_tag=method.delivery_tag)

    channel.basic_consume(queue=queue_name, on_message_callback=_on_message)
    logger.info("RabbitMQ Worker 已启动 queue=%s prefetch=%s", queue_name, PREFETCH_COUNT)
    try:
        channel.start_consuming()
    except KeyboardInterrupt:
        channel.stop_consuming()
    finally:
        connection.close()


def main() -> None:
    url = os.getenv("RABBITMQ_URL", "")
    if not url:
        logger.error("RABBITMQ_URL 未配置——Worker 无法连接 Broker，退出")
        sys.exit(1)
    consume(url)


if __name__ == "__main__":
    main()
