"""Prometheus 指标：HTTP 请求指标 + 领域事件计数器（/metrics 数据源）。

设计约束：
- prometheus-client 为可选依赖：缺失时全部记录函数降级为 no-op，
  与 Sentry 接入同哲学（观测不可用不阻断业务）；
- HTTP 路径标签用路由模板（如 /api/questions/{question_id}），绝不用
  原始路径——防 ID 级标签基数爆炸拖垮时序库；
- /metrics 端点默认公开（Prometheus 标准做法），生产部署应在网关层
  限制来源访问。
"""
from __future__ import annotations

from backend.utils.logging import get_logger

logger = get_logger("metrics")

try:  # 可选依赖：缺失时 no-op 降级
    from prometheus_client import (
        CONTENT_TYPE_LATEST,
        Counter,
        Histogram,
        generate_latest,
    )

    AVAILABLE = True
except ImportError:  # pragma: no cover - 依赖缺失路径
    AVAILABLE = False

if AVAILABLE:
    HTTP_REQUESTS = Counter(
        "mathmaster_http_requests_total",
        "HTTP 请求总数",
        ["method", "route", "status"],
    )
    HTTP_DURATION = Histogram(
        "mathmaster_http_request_duration_seconds",
        "HTTP 请求耗时（秒）",
        ["method", "route"],
        buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
    )
    QUESTIONS_CREATED = Counter(
        "mathmaster_questions_created_total",
        "错题录入总数",
        ["source"],
    )
    REVIEWS_GRADED = Counter(
        "mathmaster_reviews_graded_total",
        "复习评分总数",
        ["grade"],
    )
    AGENT_TOOL_CALLS = Counter(
        "mathmaster_agent_tool_calls_total",
        "Agent 工具调用总数",
        ["tool", "result"],
    )
    AI_CALLS = Counter(
        "mathmaster_ai_calls_total",
        "AI 模型调用总数",
        ["operation", "result"],
    )
    DEGRADED_EVENTS = Counter(
        "mathmaster_degraded_events_total",
        "降级防线事件数（静默失效变可观测）",
        ["operation"],
    )
    JOBS_SUBMITTED = Counter(
        "mathmaster_jobs_submitted_total",
        "异步任务提交总数",
    )


def observe_http(method: str, route: str, status: int, duration_seconds: float) -> None:
    """记录一次 HTTP 请求（路由模板标签 + 耗时直方图）。"""
    if not AVAILABLE:
        return
    HTTP_REQUESTS.labels(method=method, route=route, status=str(status)).inc()
    HTTP_DURATION.labels(method=method, route=route).observe(duration_seconds)


def record_question_created(source: str) -> None:
    if not AVAILABLE:
        return
    QUESTIONS_CREATED.labels(source=source).inc()


def record_review_graded(grade: str) -> None:
    if not AVAILABLE:
        return
    REVIEWS_GRADED.labels(grade=grade).inc()


def record_agent_tool_call(tool: str, result: str) -> None:
    if not AVAILABLE:
        return
    AGENT_TOOL_CALLS.labels(tool=tool, result=result).inc()


def record_ai_call(operation: str, ok: bool) -> None:
    if not AVAILABLE:
        return
    AI_CALLS.labels(operation=operation, result="ok" if ok else "error").inc()


def record_degraded_event(operation: str) -> None:
    if not AVAILABLE:
        return
    DEGRADED_EVENTS.labels(operation=operation).inc()


def record_job_submitted() -> None:
    if not AVAILABLE:
        return
    JOBS_SUBMITTED.inc()


def render_metrics() -> tuple[str, str]:
    """生成 /metrics 响应体与 Content-Type；依赖缺失时空体纯文本。"""
    if not AVAILABLE:
        return "", "text/plain; version=0.0.4"
    return generate_latest().decode("utf-8"), CONTENT_TYPE_LATEST
