"""登录失败限流器：接口 + 进程内实现（多实例部署可换 Redis 等共享存储）。"""
from __future__ import annotations

import time
from collections import defaultdict
from typing import Protocol, runtime_checkable


@runtime_checkable
class RateLimiter(Protocol):
    """限流器协议：记录失败、判断是否锁定、成功后清零。"""

    def is_locked(self, key: str) -> bool: ...

    def record_failure(self, key: str) -> None: ...

    def reset(self, key: str) -> None: ...


class InMemoryRateLimiter:
    """内存级实现：同一 key 在时间窗口内失败超限后临时锁定。

    适用于单进程部署（Streamlit / 单 uvicorn 实例）。
    """

    def __init__(self, max_failures: int = 5, window_seconds: int = 300):
        self.max_failures = max_failures
        self.window_seconds = window_seconds
        self._failures: dict[str, list[float]] = defaultdict(list)

    def is_locked(self, key: str) -> bool:
        now = time.monotonic()
        recent = [t for t in self._failures[key] if now - t < self.window_seconds]
        self._failures[key] = recent
        return len(recent) >= self.max_failures

    def record_failure(self, key: str) -> None:
        self._failures[key].append(time.monotonic())

    def reset(self, key: str) -> None:
        self._failures.pop(key, None)
