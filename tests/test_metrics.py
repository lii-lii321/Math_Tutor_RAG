"""Prometheus /metrics 端点与领域计数器测试。

prometheus-client 为常驻依赖后指标全程可用；计数器是进程级全局状态，
断言用「动作前后采样值差」而非绝对值，避免测试间串扰。
"""
from __future__ import annotations

import re

import pytest

prometheus_client = pytest.importorskip("prometheus_client")


def _sample(name: str, **labels) -> float:
    from prometheus_client import REGISTRY

    value = REGISTRY.get_sample_value(name, labels or None)
    return value if value is not None else 0.0


def test_metrics_endpoint_exposes_counters(client):
    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert "text/plain" in resp.headers["content-type"]
    body = resp.text
    assert "mathmaster_http_requests_total" in body
    assert "mathmaster_questions_created_total" in body


def test_http_counter_uses_route_template_not_raw_path(client):
    """路径标签必须是路由模板：/api/questions/999999 不得成为标签值。

    注意标签取 scope["route"].path，是 router 相对路径（不含 /api 前缀）。
    """
    login = client.post(
        "/api/auth/login", json={"username": "demo", "password": "demo123"}
    )
    assert login.status_code == 200, login.text
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    before = _sample(
        "mathmaster_http_requests_total",
        method="GET",
        route="/questions/{question_id}",
        status="404",
    )
    client.get("/api/questions/99999999", headers=headers)
    after = _sample(
        "mathmaster_http_requests_total",
        method="GET",
        route="/questions/{question_id}",
        status="404",
    )
    assert after == before + 1
    # 原始 ID 路径不得出现在 HTTP 计数器标签里（基数爆炸防线）。
    # 注意：只扫 http 计数器行——_created 等浮点时间戳的十进制表示
    # 可能天然含该数字串，全文本扫描会随机误报（CI 3.10 实测）。
    metrics_text = client.get("/metrics").text
    http_lines = [
        line for line in metrics_text.splitlines()
        if line.startswith("mathmaster_http_requests_total")
    ]
    assert http_lines
    assert not any("99999999" in line for line in http_lines)


def test_question_created_counter_increments(question_service, student_user):
    source = "manual"
    before = _sample("mathmaster_questions_created_total", source=source)
    question_service.create_manual_question(
        student_user.id, content_markdown="指标测试题 counter_probe"
    )
    after = _sample("mathmaster_questions_created_total", source=source)
    assert after == before + 1


def test_review_graded_counter_increments(question_service, student_user):
    q = question_service.create_manual_question(
        student_user.id, content_markdown="指标复习题 grade_probe", answer="x=1"
    )
    before = _sample("mathmaster_reviews_graded_total", grade="good")
    assert question_service.grade_review(q.id, student_user.id, "good") is not None
    after = _sample("mathmaster_reviews_graded_total", grade="good")
    assert after == before + 1


def test_agent_tool_call_counter_labels(student_user):
    from backend.services.agent import AgentSession, reset_write_limiters

    reset_write_limiters()
    session = AgentSession(user_id=student_user.id)
    session._execute_tool("search_questions", '{"keyword": "指标探针", "limit": 1}')
    ok_value = _sample(
        "mathmaster_agent_tool_calls_total", tool="search_questions", result="ok"
    )
    assert ok_value >= 1

    bad = session._execute_tool("no_such_tool", "{}")
    assert bad.startswith("ERROR[param]")
    assert _sample(
        "mathmaster_agent_tool_calls_total", tool="no_such_tool", result="param"
    ) >= 1


def test_ai_call_counter_on_track():
    """AI 调用计数随 track_ai_call 递增（成败各一档）。"""
    from prometheus_client import REGISTRY

    from backend.services.ai.telemetry import track_ai_call

    with track_ai_call("metrics_probe_ok") as ctx:
        ctx["ok"] = True
    assert _sample("mathmaster_ai_calls_total", operation="metrics_probe_ok", result="ok") >= 1

    with pytest.raises(RuntimeError):
        with track_ai_call("metrics_probe_err"):
            raise RuntimeError("boom")
    assert _sample(
        "mathmaster_ai_calls_total", operation="metrics_probe_err", result="error"
    ) >= 1
    assert REGISTRY  # 导入即有效


def test_histogram_buckets_present(client):
    body = client.get("/metrics").text
    assert re.search(
        r"mathmaster_http_request_duration_seconds_bucket", body
    )
