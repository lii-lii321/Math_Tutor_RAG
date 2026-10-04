"""降级防线测试：reaper 状态回收 / Redis 限流回退 / 验证器异常告警留痕。

对应提升报告路线 #2、#3：降级叙事的每一分支都要有测试守护，
静默降级处必须留痕可观测。
"""
from __future__ import annotations

import datetime as dt

from backend.database import SessionLocal
from backend.models.orm import Job
from backend.services.job_service import JobService


def _make_job(job_id: str, status: str, age_minutes: int) -> None:
    with SessionLocal() as session:
        session.add(
            Job(
                id=job_id,
                user_id=1,
                type="analyze_image",
                status=status,
                payload={"image_path": ""},
                created_at=dt.datetime.now(dt.timezone.utc)
                - dt.timedelta(minutes=age_minutes),
            )
        )
        session.commit()


def _get_job(job_id: str) -> Job | None:
    with SessionLocal() as session:
        return (
            session.query(Job).filter_by(id=job_id).first()
        )


def test_reap_stuck_jobs_marks_timed_out_running_failed():
    _make_job("reap-old-running", "running", age_minutes=60)
    _make_job("reap-fresh-running", "running", age_minutes=1)
    _make_job("reap-old-pending", "pending", age_minutes=60)

    count = JobService.reap_stuck_jobs(timeout_minutes=30)

    assert count >= 1
    old = _get_job("reap-old-running")
    assert old is not None and old.status == "failed"
    assert "超时" in (old.error or "")
    assert old.finished_at is not None
    # 新鲜 running 与 pending 不受影响
    fresh = _get_job("reap-fresh-running")
    assert fresh is not None and fresh.status == "running"
    pending = _get_job("reap-old-pending")
    assert pending is not None and pending.status == "pending"


def test_reap_stuck_jobs_returns_zero_when_queue_clean():
    count = JobService.reap_stuck_jobs(timeout_minutes=30)
    assert count == 0


def test_get_rate_limiter_falls_back_to_inmemory_when_redis_broken(monkeypatch):
    from backend.config import get_settings

    from api import deps

    monkeypatch.setenv("RATE_LIMIT_BACKEND", "redis")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6399/0")

    attempted: list[tuple] = []

    def _boom(url, *, max_requests, window_seconds):
        attempted.append((url, max_requests, window_seconds))
        raise ConnectionError("redis 不可达")

    import backend.utils.request_limiter as rl

    monkeypatch.setattr(rl, "RedisRequestRateLimiter", _boom)
    saved = dict(deps._limiters)
    deps._limiters.clear()
    get_settings.cache_clear()
    try:
        limiter = deps.get_rate_limiter("fallback_test2", 5)
        # 确认确实尝试过 Redis 后端并按配置传参，而非空转走 memory 分支
        assert attempted == [("redis://localhost:6399/0", 5, 60)]
        assert type(limiter) is rl.RequestRateLimiter
        # 兜底限流器确实在计数放行
        assert limiter.allow("fallback_test2:1") is True
    finally:
        deps._limiters.clear()
        deps._limiters.update(saved)
        get_settings.cache_clear()


def test_verifier_exception_recorded_to_telemetry(tmp_path, monkeypatch):
    from backend.services.ai import telemetry
    from backend.services.math_verifier import answer_verifier as av

    def _explode(_q, _s, _a):
        raise RuntimeError("boom-for-test")

    monkeypatch.setattr(av, "_VERIFIERS", (("exploding", _explode),))
    records: list[dict] = []
    monkeypatch.setattr(telemetry, "_write", records.append)

    result = av.verify_answer("题面", "解法", "答案")

    assert result.status == "uncertain"
    assert len(records) == 1
    record = records[0]
    assert record["operation"] == "math_verify_error:exploding"
    assert "RuntimeError" in record["error"]
    assert record["ok"] is False
