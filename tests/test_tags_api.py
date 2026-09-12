"""标签管理 API 测试。"""
from __future__ import annotations

import pytest


@pytest.fixture
def student_headers(client):
    client.post(
        "/api/auth/register",
        json={"username": "tags_user", "password": "secret1", "role": "student"},
    )
    login = client.post(
        "/api/auth/login", json={"username": "tags_user", "password": "secret1"}
    )
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def test_tags_usage_rename_delete(client, student_headers):
    _ = client.post(
        "/api/questions/text",
        headers=student_headers,
        json={"content_markdown": "标签 API 测试题", "tags": ["标签A"]},
    )

    usage = client.get("/api/tags", headers=student_headers)
    assert usage.status_code == 200
    assert usage.json().get("标签A") == 1

    renamed = client.post(
        "/api/tags/rename",
        headers=student_headers,
        json={"old": "标签A", "new": "标签B"},
    )
    assert renamed.status_code == 200
    assert renamed.json()["updated"] >= 1

    usage_after = client.get("/api/tags", headers=student_headers)
    assert usage_after.json().get("标签B") == 1

    deleted = client.delete("/api/tags/标签B", headers=student_headers)
    assert deleted.status_code == 200

    usage_final = client.get("/api/tags", headers=student_headers)
    assert usage_final.json().get("标签B") is None

    noop = client.post(
        "/api/tags/rename",
        headers=student_headers,
        json={"old": "标签B", "new": "标签B"},
    )
    assert noop.status_code == 200  # 同名重命名是合法空操作
    assert noop.json()["updated"] == 0


def test_tags_endpoints_require_auth(client):
    assert client.get("/api/tags").status_code == 401
