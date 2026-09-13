"""批注 API 测试。"""
from __future__ import annotations

import pytest


@pytest.fixture
def student_headers(client):
    client.post(
        "/api/auth/register",
        json={"username": "comment_user", "password": "secret1", "role": "student"},
    )
    login = client.post(
        "/api/auth/login", json={"username": "comment_user", "password": "secret1"}
    )
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


@pytest.fixture
def question_id(client, student_headers):
    created = client.post(
        "/api/questions/text",
        headers=student_headers,
        json={"content_markdown": "批注 API 测试题", "tags": ["批注"]},
    )
    return created.json()["id"]


def test_comment_crud_api(client, student_headers, question_id):
    added = client.post(
        f"/api/questions/{question_id}/comments",
        headers=student_headers,
        json={"content": "这道题的易错点在判别式"},
    )
    assert added.status_code == 201

    listed = client.get(f"/api/questions/{question_id}/comments", headers=student_headers)
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    comment_id = listed.json()[0]["id"]
    deleted = client.delete(
        f"/api/questions/{question_id}/comments/{comment_id}", headers=student_headers
    )
    assert deleted.status_code == 204

    assert client.get(f"/api/questions/{question_id}/comments", headers=student_headers).json() == []


def test_comment_requires_auth(client, question_id):
    assert client.get(f"/api/questions/{question_id}/comments").status_code == 401
