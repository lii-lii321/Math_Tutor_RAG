"""RabbitMQ 队列后端测试（提升项：真 MQ 三件套之一）。

pika 为可选依赖，测试用 fake pika 模块注入 sys.modules——验证发布语义
（durable 队列声明、持久化消息体、断线重连重投）与 Worker 消息分发，
不依赖真实 Broker；真实 Broker 冒烟见 docker compose --profile rabbitmq。
"""
from __future__ import annotations

import json
import sys
import types

from backend.jobs.queue import (
    QUEUE_NAME,
    RabbitMQJobQueue,
    ThreadedJobQueue,
    get_job_queue,
)
from backend.utils.logging import get_logger

logger = get_logger("test")


class _FakeChannel:
    def __init__(self, state):
        self.state = state

    def queue_declare(self, queue, durable):
        self.state["declared"].append((queue, durable))

    def basic_publish(self, exchange, routing_key, body, properties):
        self.state["published"].append(
            {
                "exchange": exchange,
                "routing_key": routing_key,
                "body": json.loads(body.decode("utf-8")),
                "delivery_mode": properties.delivery_mode,
            }
        )


class _FakeConnection:
    def __init__(self, state):
        self.state = state
        self.is_closed = False

    def channel(self):
        self.state["channels_opened"] += 1
        return _FakeChannel(self.state)

    def close(self):
        self.is_closed = True


def _install_fake_pika(monkeypatch):
    state = {"declared": [], "published": [], "channels_opened": 0}

    class _FakePika(types.ModuleType):
        @staticmethod
        def BlockingConnection(parameters):
            state["connections_created"] = state.get("connections_created", 0) + 1
            return _FakeConnection(state)

        @staticmethod
        def URLParameters(url):
            state["url"] = url
            return {"url": url}

        class BasicProperties:
            def __init__(self, **kwargs):
                self.__dict__.update(kwargs)

    fake = _FakePika("pika")
    monkeypatch.setitem(sys.modules, "pika", fake)
    return state


def test_publish_declares_durable_queue_and_persistent_message(monkeypatch):
    state = _install_fake_pika(monkeypatch)
    queue = RabbitMQJobQueue("amqp://guest:guest@localhost:5672/")
    queue.submit_analyze("job-1", 42)

    assert state["declared"] == [(QUEUE_NAME, True)]
    assert state["url"].startswith("amqp://")
    assert state["published"] == [
        {
            "exchange": "",
            "routing_key": QUEUE_NAME,
            "body": {"job_id": "job-1", "user_id": 42},
            "delivery_mode": 2,  # persistent
        }
    ]
    assert state["connections_created"] == 1


def test_connection_reused_across_publishes(monkeypatch):
    state = _install_fake_pika(monkeypatch)
    queue = RabbitMQJobQueue("amqp://guest:guest@localhost:5672/")
    queue.submit_analyze("job-a", 1)
    queue.submit_analyze("job-b", 2)
    assert state["connections_created"] == 1  # 复用连接，不逐条重连


def test_reconnect_once_when_connection_dies(monkeypatch):
    state = _install_fake_pika(monkeypatch)

    real_publish = _FakeChannel.basic_publish

    def flaky_publish(self, *args, **kwargs):
        if self.state["channels_opened"] == 1 and not self.state["published"]:
            self.state["dropped"] = True
            raise ConnectionError("broken pipe")
        return real_publish(self, *args, **kwargs)

    monkeypatch.setattr(_FakeChannel, "basic_publish", flaky_publish)
    queue = RabbitMQJobQueue("amqp://guest:guest@localhost:5672/")
    queue.submit_analyze("job-retry", 7)

    assert state.get("dropped") is True
    assert state["connections_created"] == 2  # 重连一次
    assert [p["body"]["job_id"] for p in state["published"]] == ["job-retry"]


def test_worker_handle_message_dispatches(monkeypatch):
    """Worker 消息处理：JSON 解析 → run_analyze_job(job_id, user_id)。"""
    from backend.jobs import rabbitmq_worker, tasks

    calls: list[tuple[str, int]] = []
    monkeypatch.setattr(
        tasks, "run_analyze_job", lambda job_id, user_id: calls.append((job_id, user_id))
    )
    rabbitmq_worker.handle_message(
        json.dumps({"job_id": "w-1", "user_id": 9}).encode("utf-8")
    )
    assert calls == [("w-1", 9)]


def test_factory_priority_rabbitmq_over_redis(monkeypatch):
    _install_fake_pika(monkeypatch)
    queue = get_job_queue(
        redis_url="redis://localhost:6379/0",
        rabbitmq_url="amqp://guest:guest@localhost:5672/",
    )
    assert isinstance(queue, RabbitMQJobQueue)


def test_factory_falls_back_to_thread_when_pika_missing(monkeypatch):
    # 屏蔽真实 pika（如已安装）：模拟可选依赖缺失
    monkeypatch.setitem(sys.modules, "pika", None)
    queue = get_job_queue(rabbitmq_url="amqp://guest:guest@localhost:5672/")
    assert isinstance(queue, ThreadedJobQueue)


def test_factory_defaults_to_thread():
    assert isinstance(get_job_queue(), ThreadedJobQueue)
