"""批注 API 测试。"""
from __future__ import annotations

import pytest


def _login_headers(client, username: str, password: str) -> dict:
    login = client.post(
        "/api/auth/login", json={"username": username, "password": password}
    )
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def _register(client, username: str, role: str) -> dict:
    payload = {"username": username, "password": "secret1", "role": role}
    if role == "teacher":
        payload["invite_code"] = "test-invite-code"
    client.post("/api/auth/register", json=payload)
    return _login_headers(client, username, "secret1")


@pytest.fixture
def student_headers(client):
    return _register(client, "comment_user", "student")


@pytest.fixture
def other_student_headers(client):
    return _register(client, "comment_other", "student")


@pytest.fixture
def teacher_headers(client):
    return _register(client, "comment_teacher_user", "teacher")


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


def test_student_cannot_read_other_private_question_comments(
    client, student_headers, question_id, other_student_headers
):
    client.post(
        f"/api/questions/{question_id}/comments",
        headers=student_headers,
        json={"content": "学生A 的私题批注"},
    )
    listed = client.get(
        f"/api/questions/{question_id}/comments", headers=other_student_headers
    )
    assert listed.status_code == 404


def test_student_cannot_comment_on_other_question(
    client, student_headers, question_id, other_student_headers
):
    added = client.post(
        f"/api/questions/{question_id}/comments",
        headers=student_headers,
        json={"content": "学生A 自己的批注"},
    )
    assert added.status_code == 201

    intruded = client.post(
        f"/api/questions/{question_id}/comments",
        headers=other_student_headers,
        json={"content": "路人留言"},
    )
    assert intruded.status_code == 404

    listed = client.get(f"/api/questions/{question_id}/comments", headers=student_headers)
    assert [c["content"] for c in listed.json()] == ["学生A 自己的批注"]


def test_student_cannot_delete_other_students_comment(
    client, student_headers, question_id, other_student_headers
):
    client.post(
        f"/api/questions/{question_id}/comments",
        headers=student_headers,
        json={"content": "待保护的批注"},
    )
    comment_id = client.get(
        f"/api/questions/{question_id}/comments", headers=student_headers
    ).json()[0]["id"]

    deleted = client.delete(
        f"/api/questions/{question_id}/comments/{comment_id}",
        headers=other_student_headers,
    )
    assert deleted.status_code == 404

    listed = client.get(f"/api/questions/{question_id}/comments", headers=student_headers)
    assert len(listed.json()) == 1


def test_teacher_can_read_and_delete_student_comments(
    client, student_headers, question_id, teacher_headers
):
    client.post(
        f"/api/questions/{question_id}/comments",
        headers=student_headers,
        json={"content": "老师请看这里"},
    )
    listed = client.get(f"/api/questions/{question_id}/comments", headers=teacher_headers)
    assert listed.status_code == 200
    assert [c["content"] for c in listed.json()] == ["老师请看这里"]

    comment_id = listed.json()[0]["id"]
    deleted = client.delete(
        f"/api/questions/{question_id}/comments/{comment_id}", headers=teacher_headers
    )
    assert deleted.status_code == 204
    assert client.get(f"/api/questions/{question_id}/comments", headers=student_headers).json() == []


def test_teacher_can_comment_on_student_question(
    client, student_headers, question_id, teacher_headers
):
    added = client.post(
        f"/api/questions/{question_id}/comments",
        headers=teacher_headers,
        json={"content": "教师批语：注意第二问的分类讨论"},
    )
    assert added.status_code == 201

    listed = client.get(f"/api/questions/{question_id}/comments", headers=student_headers)
    assert listed.status_code == 200
    assert [c["content"] for c in listed.json()] == ["教师批语：注意第二问的分类讨论"]
    assert listed.json()[0]["role"] == "teacher"


def test_missing_question_returns_404_for_owner(client, student_headers):
    listed = client.get("/api/questions/999999/comments", headers=student_headers)
    assert listed.status_code == 404
    added = client.post(
        "/api/questions/999999/comments", headers=student_headers, json={"content": "内容"}
    )
    assert added.status_code == 404
