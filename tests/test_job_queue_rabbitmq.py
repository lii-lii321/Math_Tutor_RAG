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
    """发布侧 + 消费侧通用的假通道（consume 路径缺的方法按需补齐）。"""

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

    def basic_qos(self, prefetch_count):
        self.state["qos"] = prefetch_count

    def basic_consume(self, queue, on_message_callback):
        self.state["consumed_queue"] = queue
        self.state["on_message"] = on_message_callback

    def basic_ack(self, delivery_tag):
        self.state["acked"].append(delivery_tag)

    def start_consuming(self):
        self.state["started"] = True  # 立即返回：不阻塞测试

    def stop_consuming(self):
        self.state["stopped"] = True


class _FakeConnection:
    def __init__(self, state):
        self.state = state
        self.is_closed = False

    def channel(self):
        self.state["channels_opened"] += 1
        return _FakeChannel(self.state)

    def close(self):
        self.is_closed = True
        self.state["closed"] = True


def _install_fake_pika(monkeypatch):
    state = {
        "declared": [],
        "published": [],
        "channels_opened": 0,
        "acked": [],
        "closed": False,
        "started": False,
        "stopped": False,
        "qos": None,
        "consumed_queue": None,
        "on_message": None,
    }

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


class TestWorkerConsume:
    """消费循环接线测试（37% 覆盖薄弱点补齐）：声明/qos/ack 语义/优雅停止。"""

    def test_consume_wires_durable_queue_qos_and_callback(self, monkeypatch):
        state = _install_fake_pika(monkeypatch)
        from backend.jobs import rabbitmq_worker

        rabbitmq_worker.consume("amqp://guest:guest@localhost:5672/")
        assert state["declared"] == [(QUEUE_NAME, True)]
        assert state["qos"] == rabbitmq_worker.PREFETCH_COUNT == 1
        assert state["consumed_queue"] == QUEUE_NAME
        assert callable(state["on_message"])
        assert state["started"] is True
        assert state["closed"] is True  # start_consuming 立即返回 → 优雅关闭

    def test_callback_dispatches_and_acks_on_success(self, monkeypatch):
        state = _install_fake_pika(monkeypatch)
        from backend.jobs import rabbitmq_worker, tasks

        calls: list[tuple[str, int]] = []
        monkeypatch.setattr(
            tasks, "run_analyze_job", lambda job_id, user_id: calls.append((job_id, user_id))
        )
        rabbitmq_worker.consume("amqp://guest:guest@localhost:5672/")
        channel = _FakeChannel(state)
        method = type("M", (), {"delivery_tag": 7})()
        state["on_message"](channel, method, None, b'{"job_id":"c-1","user_id":5}')
        assert calls == [("c-1", 5)]
        assert state["acked"] == [7]

    def test_callback_acks_even_when_handler_raises(self, monkeypatch):
        """处理失败也必须 ack：任务状态在 jobs 表，requeue 只会重复昂贵 AI 调用。"""
        state = _install_fake_pika(monkeypatch)
        from backend.jobs import rabbitmq_worker, tasks

        def _boom(job_id, user_id):
            raise RuntimeError("task failed")

        monkeypatch.setattr(tasks, "run_analyze_job", _boom)
        rabbitmq_worker.consume("amqp://guest:guest@localhost:5672/")
        channel = _FakeChannel(state)
        method = type("M", (), {"delivery_tag": 3})()
        # 异常不得外抛（消费循环存续），且仍 ack
        state["on_message"](channel, method, None, b'{"job_id":"c-2","user_id":5}')
        assert state["acked"] == [3]

    def test_keyboard_interrupt_stops_gracefully(self, monkeypatch):
        state = _install_fake_pika(monkeypatch)
        from backend.jobs import rabbitmq_worker

        class _InterruptingChannel(_FakeChannel):
            def start_consuming(self):
                raise KeyboardInterrupt()

        class _InterruptingConnection(_FakeConnection):
            def channel(self):
                self.state["channels_opened"] += 1
                return _InterruptingChannel(self.state)

        monkeypatch.setattr(
            sys.modules["pika"],
            "BlockingConnection",
            lambda parameters: _InterruptingConnection(state),
        )
        # KeyboardInterrupt 不外抛：优雅 stop + close
        rabbitmq_worker.consume("amqp://guest:guest@localhost:5672/")
        assert state["stopped"] is True
        assert state["closed"] is True


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
