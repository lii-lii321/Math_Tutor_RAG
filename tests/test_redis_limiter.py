"""Redis 限流器测试（注入 fake redis 客户端，无需真实 Redis）。"""
from __future__ import annotations

from backend.utils.rate_limit import RateLimiter, RedisRateLimiter


class _FakePipeline:
    def __init__(self, store: dict, ttls: dict):
        self._store = store
        self._ttls = ttls
        self._ops: list = []

    def incr(self, key):
        self._ops.append(("incr", key))
        return self

    def expire(self, key, seconds, nx=False):
        self._ops.append(("expire", key, seconds, nx))
        return self

    def execute(self):
        result = []
        for op in self._ops:
            if op[0] == "incr":
                self._store[op[1]] = self._store.get(op[1], 0) + 1
                result.append(self._store[op[1]])
            elif op[0] == "expire":
                if op[3] and op[1] in self._ttls:
                    continue
                self._ttls[op[1]] = op[2]
        self._ops = []
        return result


class _FakeRedis:
    """最小 INCR/EXPIRE/DELETE/GET/PIPELINE 语义。"""

    def __init__(self):
        self.store: dict[str, int] = {}
        self.ttls: dict[str, int] = {}

    def pipeline(self):
        return _FakePipeline(self.store, self.ttls)

    def get(self, key):
        return self.store.get(key)

    def delete(self, key):
        self.store.pop(key, None)


def test_redis_rate_limiter_flow():
    client = _FakeRedis()
    limiter = RedisRateLimiter(max_failures=3, client=client)
    assert isinstance(limiter, RateLimiter)

    assert not limiter.is_locked("user1")
    for _ in range(3):
        limiter.record_failure("user1")
    assert limiter.is_locked("user1")
    assert not limiter.is_locked("user2")

    limiter.reset("user1")
    assert not limiter.is_locked("user1")


def test_redis_rate_limiter_expiry_window_set_once():
    client = _FakeRedis()
    limiter = RedisRateLimiter(window_seconds=300, client=client)
    limiter.record_failure("user1")
    limiter.record_failure("user1")
    assert client.ttls["mathmaster:login_fail:user1"] == 300
    assert client.store["mathmaster:login_fail:user1"] == 2
