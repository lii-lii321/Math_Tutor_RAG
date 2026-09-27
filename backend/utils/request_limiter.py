"""进程内滑动窗口请求限流器（Batch 10）：保护 AI/上传等高成本端点。

与登录失败锁定（rate_limit.py）不同，这里是通用的「每 key 每窗口 N 次」计数；
多实例部署时可将 allow() 换成 Redis INCR+EXPIRE 实现（接口保持）。
"""
from __future__ import annotations

import time
from collections import defaultdict, deque


class RequestRateLimiter:
    """滑动窗口计数：同一 key 在 window_seconds 内最多 max_requests 次。"""

    def __init__(self, max_requests: int, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        window_start = now - self.window_seconds
        hits = self._hits[key]
        while hits and hits[0] <= window_start:
            hits.popleft()
        if len(hits) >= self.max_requests:
            return False
        hits.append(now)
        return True

    def remaining(self, key: str) -> int:
        """当前窗口剩余配额（用于诊断与测试）。"""
        now = time.monotonic()
        hits = self._hits[key]
        while hits and hits[0] <= now - self.window_seconds:
            hits.popleft()
        return max(0, self.max_requests - len(hits))


class NoopRequestRateLimiter:
    """不限流实现（limit=0 时使用）。"""

    def allow(self, key: str) -> bool:
        return True

    def remaining(self, key: str) -> int:
        return -1
