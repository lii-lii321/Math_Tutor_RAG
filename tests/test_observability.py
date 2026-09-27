"""观测摘要端点测试（手册 §十一）。"""
from __future__ import annotations

import uuid


def test_observability_summary(client):
    username = f"obs_{uuid.uuid4().hex[:10]}"
    client.post(
        "/api/auth/register",
        json={"username": username, "password": "secret1", "role": "student"},
    )
    login = client.post(
        "/api/auth/login", json={"username": username, "password": "secret1"}
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    response = client.get("/api/stats/observability", headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert {"calls", "success_rate", "avg_latency_ms", "by_operation"} <= set(body["ai"])
    assert {"total", "failed", "failure_rate"} <= set(body["jobs"])
    assert body["jobs"]["total"] >= 0

    assert client.get("/api/stats/observability").status_code == 401
