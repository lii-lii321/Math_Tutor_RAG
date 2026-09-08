"""FastAPI 网关集成测试。"""
from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from api.main import create_app


@pytest.fixture(scope="module")
def client():
    return TestClient(create_app())


def _auth_header(client: TestClient, username: str, password: str) -> dict:
    resp = client.post(
        "/api/auth/login", json={"username": username, "password": password}
    )
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _tiny_jpeg() -> bytes:
    image = Image.new("RGB", (10, 10), (120, 160, 220))
    stream = io.BytesIO()
    image.save(stream, format="JPEG")
    return stream.getvalue()


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_login_wrong_password(client):
    resp = client.post(
        "/api/auth/login", json={"username": "demo", "password": "nope"}
    )
    assert resp.status_code == 401


def test_register_and_login_roundtrip(client):
    reg = client.post(
        "/api/auth/register",
        json={"username": "api_user", "password": "secret1", "role": "student"},
    )
    assert reg.status_code == 201
    token = reg.json()["access_token"]
    assert token

    login = client.post(
        "/api/auth/login", json={"username": "api_user", "password": "secret1"}
    )
    assert login.status_code == 200
    assert login.json()["user_id"] == reg.json()["user_id"]


def test_protected_endpoint_requires_token(client):
    assert client.get("/api/questions").status_code == 401
    assert client.get("/api/questions", headers={"Authorization": "Bearer bad"}).status_code == 401


def test_text_question_crud_flow(client):
    headers = _auth_header(client, "api_user", "secret1")

    created = client.post(
        "/api/questions/text",
        headers=headers,
        json={
            "content_markdown": "求 $x^2-4=0$ 的解。",
            "answer": "x=±2",
            "tags": ["方程"],
            "knowledge_points": ["一元二次方程"],
        },
    )
    assert created.status_code == 201, created.text
    question = created.json()
    assert question["source"] == "manual"
    qid = question["id"]

    listed = client.get("/api/questions", headers=headers)
    assert listed.status_code == 200
    assert any(q["id"] == qid for q in listed.json())

    patched = client.patch(
        f"/api/questions/{qid}",
        headers=headers,
        json={"answer": "$x=\\pm 2$"},
    )
    assert patched.status_code == 200
    assert patched.json()["answer"] == "$x=\\pm 2$"

    deleted = client.delete(f"/api/questions/{qid}", headers=headers)
    assert deleted.status_code == 204
    assert client.get(f"/api/questions/{qid}", headers=headers).status_code == 404


def test_analyze_with_mock_provider(client):
    headers = _auth_header(client, "api_user", "secret1")
    resp = client.post(
        "/api/questions/analyze",
        headers=headers,
        files={"image": ("q.jpg", _tiny_jpeg(), "image/jpeg")},
        data={"tags": "期末复习", "hint": ""},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["question"]["id"] > 0
    assert body["analysis"]["knowledge_points"]
    assert body["question"]["tags"][0] == "期末复习"


def test_analyze_rejects_bad_mime(client):
    headers = _auth_header(client, "api_user", "secret1")
    resp = client.post(
        "/api/questions/analyze",
        headers=headers,
        files={"image": ("q.txt", b"not-an-image", "text/plain")},
    )
    assert resp.status_code == 415


def test_review_grade_flow(client):
    headers = _auth_header(client, "api_user", "secret1")

    created = client.post(
        "/api/questions/text",
        headers=headers,
        json={"content_markdown": "解不等式 $x+1>0$", "answer": "x>-1"},
    )
    qid = created.json()["id"]

    due = client.get("/api/review/due", headers=headers)
    assert due.status_code == 200
    assert any(q["id"] == qid for q in due.json())

    graded = client.post(
        f"/api/review/{qid}/grade", headers=headers, json={"grade": "good"}
    )
    assert graded.status_code == 200
    assert graded.json()["reps"] == 1

    bad = client.post(
        f"/api/review/{qid}/grade", headers=headers, json={"grade": "perfect"}
    )
    assert bad.status_code == 422


def test_followup_ownership_isolated(client):
    headers_a = _auth_header(client, "api_user", "secret1")
    created = client.post(
        "/api/questions/text",
        headers=headers_a,
        json={"content_markdown": "三角形内角和问题", "answer": "180°"},
    )
    qid = created.json()["id"]

    follow = client.post(
        f"/api/review/{qid}/followup",
        headers=headers_a,
        json={"question": "为什么内角和是180度？", "history": []},
    )
    assert follow.status_code == 200
    assert follow.json()["reply"]

    _ = client.post(
        "/api/auth/register",
        json={"username": "api_other", "password": "secret1"},
    )
    headers_b = _auth_header(client, "api_other", "secret1")
    denied = client.post(
        f"/api/review/{qid}/followup",
        headers=headers_b,
        json={"question": "偷看", "history": []},
    )
    assert denied.status_code == 404


def test_export_word_exam_endpoint(client):
    headers = _auth_header(client, "api_user", "secret1")
    resp = client.get("/api/questions/export/docx", headers=headers)
    assert resp.status_code == 200
    assert resp.content[:2] == b"PK"  # docx 本质是 zip

    empty = client.get(
        "/api/questions/export/docx",
        headers=headers,
        params={"keyword": "不存在的关键词xyz"},
    )
    assert empty.status_code == 404


def test_stats_endpoints(client):
    headers = _auth_header(client, "api_user", "secret1")
    dash = client.get("/api/stats/dashboard", headers=headers)
    assert dash.status_code == 200
    assert dash.json()["total"] >= 1

    graph = client.get("/api/stats/tag-graph", headers=headers)
    assert graph.status_code == 200
    assert isinstance(graph.json(), list)


def test_export_and_import_endpoint(client):
    headers = _auth_header(client, "api_user", "secret1")

    exported = client.get("/api/questions/export", headers=headers)
    assert exported.status_code == 200
    backup = exported.json()
    assert backup["format"] == "mathmaster-backup"

    slim = {
        "format": "mathmaster-backup",
        "version": 1,
        "questions": [
            {"content_markdown": "API 导入的题目", "answer": "ok", "tags": ["api"]},
        ],
    }
    imported = client.post("/api/questions/import", headers=headers, json=slim)
    assert imported.status_code == 200
    assert imported.json()["imported"] == 1

    bad = client.post("/api/questions/import", headers=headers, json={"nope": 1})
    assert bad.status_code == 422
