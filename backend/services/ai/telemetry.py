"""AI 调用遥测：本地 JSONL 记录每次 LLM 调用（延迟/成功/提供商）。

轻量自包含方案：写 data/telemetry/ai_calls.jsonl，一行一次调用。
需要云端聚合时可将此文件接入 Langfuse 等（记录字段与其语义对齐）。
"""
from __future__ import annotations

import datetime as dt
import json
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from backend.config import get_settings
from backend.utils.logging import get_logger

logger = get_logger("telemetry")


def _telemetry_path() -> Path:
    settings = get_settings()
    path = settings.data_dir / "telemetry"
    path.mkdir(parents=True, exist_ok=True)
    return path / "ai_calls.jsonl"


@contextmanager
def track_ai_call(operation: str) -> Iterator[dict]:
    """包裹一次 AI 调用：自动记录耗时与结果。

    用法：
        with track_ai_call("analyze_image") as ctx:
            result = provider.analyze_question(...)
            ctx["ok"] = True
    """
    ctx: dict = {"ok": False, "error": None}
    start = time.perf_counter()
    try:
        yield ctx
        ctx["ok"] = True
    except Exception as exc:
        ctx["error"] = str(exc)[:300]
        raise
    finally:
        elapsed_ms = round((time.perf_counter() - start) * 1000)
        _write(
            {
                "ts": dt.datetime.now(dt.timezone.utc).isoformat(),
                "operation": operation,
                "latency_ms": elapsed_ms,
                "ok": ctx["ok"],
                "error": ctx["error"],
            }
        )


def _write(record: dict) -> None:
    try:
        with _telemetry_path().open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError as exc:  # noqa: BLE001 - 遥测失败不影响主流程
        logger.debug("遥测写入失败: %s", exc)


def read_recent(limit: int = 100) -> list[dict]:
    """读取最近 limit 条遥测记录（新→旧）。"""
    path = _telemetry_path()
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    records = []
    for line in reversed(lines[-limit:]):
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records


def summarize(limit: int = 200) -> dict:
    """汇总最近 limit 次调用：次数/成功率/平均延迟/按操作分组。"""
    records = read_recent(limit)
    if not records:
        return {"calls": 0, "success_rate": None, "avg_latency_ms": None, "by_operation": {}}
    ok = sum(1 for r in records if r.get("ok"))
    latencies = [r.get("latency_ms", 0) for r in records]
    by_op: dict[str, dict] = {}
    for r in records:
        bucket = by_op.setdefault(r.get("operation", "unknown"), {"count": 0, "avg_ms": 0})
        bucket["count"] += 1
    for op, bucket in by_op.items():
        op_latencies = [r["latency_ms"] for r in records if r.get("operation") == op]
        bucket["avg_ms"] = round(sum(op_latencies) / len(op_latencies))
    return {
        "calls": len(records),
        "success_rate": round(ok / len(records) * 100),
        "avg_latency_ms": round(sum(latencies) / len(latencies)),
        "by_operation": by_op,
    }
