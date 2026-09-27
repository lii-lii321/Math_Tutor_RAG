"""掌握度画像与今日计划 API 测试（Batch 04/05）。"""
from __future__ import annotations

import uuid

import pytest


@pytest.fixture
def kp_headers(client):
    username = f"kp_api_{uuid.uuid4().hex[:10]}"
    client.post(
        "/api/auth/register",
        json={"username": username, "password": "secret1", "role": "student"},
    )
    login = client.post(
        "/api/auth/login", json={"username": username, "password": "secret1"}
    )
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def test_mastery_and_today_api(client, kp_headers):
    created = client.post(
        "/api/questions/text",
        headers=kp_headers,
        json={
            "content_markdown": "掌握度 API 测试题",
            "knowledge_points": ["条件概率"],
            "tags": ["概率"],
        },
    )
    assert created.status_code in {200, 201}, created.text

    profile = client.get("/api/review/mastery", headers=kp_headers)
    assert profile.status_code == 200, profile.text
    items = profile.json()
    assert len(items) == 1
    entry = items[0]
    assert entry["knowledge_point"] == "条件概率"
    assert 0.0 <= entry["mastery"] <= 1.0
    assert entry["question_count"] == 1
    assert entry["status"] in {"weak", "shaky", "solid"}
    assert entry["status_label"]

    plan = client.get("/api/review/today", headers=kp_headers)
    assert plan.status_code == 200, plan.text
    rows = plan.json()
    assert len(rows) == 1
    assert rows[0]["question"]["id"] == created.json()["id"]
    assert rows[0]["reason"]
    assert isinstance(rows[0]["priority"], float)

    assert client.get("/api/review/mastery").status_code == 401
    assert client.get("/api/review/today").status_code == 401
