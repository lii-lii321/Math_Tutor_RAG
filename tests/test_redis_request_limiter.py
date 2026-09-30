"""Redis 请求限流器与后端切换测试（fakeredis 离线验证）。"""
from __future__ import annotations

from fakeredis import FakeRedis

from backend.utils.request_limiter import RedisRequestRateLimiter


class TestRedisRequestRateLimiter:
    def test_allow_within_limit_then_block(self):
        client = FakeRedis()
        limiter = RedisRequestRateLimiter(
            "redis://x/0", max_requests=3, window_seconds=60, client=client
        )
        assert [limiter.allow("u1") for _ in range(3)] == [True, True, True]
        assert limiter.allow("u1") is False
        assert limiter.remaining("u1") == 0
        assert limiter.allow("u2") is True  # 不同 key 独立计数

    def test_shared_across_instances(self):
        """两个限流器实例共享同一 Redis 计数（多实例部署语义）。"""
        client = FakeRedis()
        a = RedisRequestRateLimiter("r", max_requests=2, window_seconds=60, client=client)
        b = RedisRequestRateLimiter("r", max_requests=2, window_seconds=60, client=client)
        assert a.allow("k") and b.allow("k") and not a.allow("k")
        assert not b.allow("k")

    def test_key_namespaced(self):
        client = FakeRedis()
        limiter = RedisRequestRateLimiter("r", max_requests=5, window_seconds=60, client=client)
        limiter.allow("agent:1")
        assert client.exists("mathmaster:rl:agent:1") == 1


class TestBackendSwitch:
    def test_deps_redis_backend_uses_redis_limiter(self, monkeypatch):
        from api import deps
        from backend.config import Settings

        settings = Settings(
            rate_limit_backend="redis",
            redis_url="redis://x/0",
            rate_limit_agent_per_min=5,
            _env_file=None,
        )
        monkeypatch.setattr(deps, "get_settings", lambda: settings)
        monkeypatch.setattr(deps, "_limiters", {})
        captured = {}

        def _fake_init(self, redis_url, max_requests, window_seconds, client=None):
            captured["max"] = max_requests
            self.max_requests = max_requests
            self.window_seconds = window_seconds
            self._client = None  # 不真正连接

        import backend.utils.request_limiter as rl

        monkeypatch.setattr(rl.RedisRequestRateLimiter, "__init__", _fake_init)
        limiter = deps.get_rate_limiter("agent", 5)
        assert type(limiter).__name__ == "RedisRequestRateLimiter"
        assert captured["max"] == 5

    def test_deps_memory_backend_default(self, monkeypatch):
        from api import deps
        from backend.config import Settings

        settings = Settings(rate_limit_agent_per_min=7, _env_file=None)
        monkeypatch.setattr(deps, "get_settings", lambda: settings)
        monkeypatch.setattr(deps, "_limiters", {})
        limiter = deps.get_rate_limiter("agent", 7)
        assert type(limiter).__name__ == "RequestRateLimiter"
