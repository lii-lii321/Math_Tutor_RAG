"""完整备份 API 双端点测试：鉴权 / 导出 zip / 往返计数 / 幂等 / 超限 / 路由序。

夹具仿 test_api.py（module 级 client + 登录头 + _tiny_jpeg），
场景仿 test_full_backup.py（owner/receiver 往返）。
"""
from __future__ import annotations

import io
import json
import uuid
import zipfile

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from api.main import create_app
from api.routers import questions as questions_router
from backend.database import SessionLocal
from backend.services.question_service import QuestionService


@pytest.fixture(scope="module")
def client():
    return TestClient(create_app())


def _tiny_jpeg() -> bytes:
    image = Image.new("RGB", (10, 10), (200, 90, 60))
    stream = io.BytesIO()
    image.save(stream, format="JPEG")
    return stream.getvalue()


def _register_and_login(client: TestClient, prefix: str) -> tuple[dict, int]:
    username = f"{prefix}_{uuid.uuid4().hex[:8]}"
    reg = client.post(
        "/api/auth/register",
        json={"username": username, "password": "secret1", "role": "student"},
    )
    assert reg.status_code == 201, reg.text
    login = client.post(
        "/api/auth/login", json={"username": username, "password": "secret1"}
    )
    assert login.status_code == 200, login.text
    header = {"Authorization": f"Bearer {login.json()['access_token']}"}
    return header, reg.json()["user_id"]


def _seed_history_with_image(user_id: int) -> None:
    """建一道带图题并评分一次（MockProvider，零网络）。"""
    service = QuestionService(session_factory=SessionLocal)
    out, _analysis = service.analyze_and_save(user_id, _tiny_jpeg(), user_tags=["api备份"])
    assert service.grade_review(out.id, user_id, "good") is not None


def test_unauthorized_401(client):
    assert client.get("/api/questions/export/full").status_code == 401
    assert client.post("/api/questions/import/full").status_code == 401


def test_export_full_zip_with_manifest(client):
    """导出 200 + Content-Disposition + zip 可开且含 manifest.json。"""
    header, user_id = _register_and_login(client, "fbkexp")
    _seed_history_with_image(user_id)

    resp = client.get("/api/questions/export/full", headers=header)
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"] == "application/zip"
    assert "mathmaster_full_backup_" in resp.headers["content-disposition"]
    archive = zipfile.ZipFile(io.BytesIO(resp.content))
    assert "manifest.json" in archive.namelist()
    manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
    assert manifest["format"] == "mathmaster-full-backup"
    assert manifest["count"] == 1


def test_roundtrip_five_counts(client):
    """A 建题带图 + 评分 → 导出 → B 导入：五计数正确。"""
    header_a, user_a = _register_and_login(client, "fbk_a")
    _seed_history_with_image(user_a)

    exported = client.get("/api/questions/export/full", headers=header_a)
    header_b, user_b = _register_and_login(client, "fbk_b")
    resp = client.post(
        "/api/questions/import/full",
        headers=header_b,
        files={"file": ("backup.zip", exported.content, "application/zip")},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body == {"questions": 1, "logs": 1, "images": 1, "missing_images": 0, "skipped": 0}

    # B 侧真实落库：题目带新属主图、日志一条
    from backend.database import SessionLocal
    from backend.models.orm import Question, ReviewLog

    with SessionLocal() as session:
        restored = session.query(Question).filter_by(user_id=user_b).one()
        assert restored.image_path and f"/u{user_b}/" in restored.image_path
        assert len(session.query(ReviewLog).filter_by(user_id=user_b).all()) == 1


def test_duplicate_import_idempotent(client):
    header_a, user_a = _register_and_login(client, "fbk_dup_a")
    _seed_history_with_image(user_a)
    exported = client.get("/api/questions/export/full", headers=header_a)
    header_b, user_b = _register_and_login(client, "fbk_dup_b")

    first = client.post(
        "/api/questions/import/full",
        headers=header_b,
        files={"file": ("backup.zip", exported.content, "application/zip")},
    )
    assert first.status_code == 200 and first.json()["questions"] == 1
    second = client.post(
        "/api/questions/import/full",
        headers=header_b,
        files={"file": ("backup.zip", exported.content, "application/zip")},
    )
    assert second.status_code == 200
    assert second.json()["questions"] == 0
    assert second.json()["logs"] == 0


def test_corrupt_bytes_422(client):
    header, _uid = _register_and_login(client, "fbk_corrupt")
    resp = client.post(
        "/api/questions/import/full",
        headers=header,
        files={"file": ("backup.zip", b"definitely not a zip", "application/zip")},
    )
    assert resp.status_code == 422


def test_forged_manifest_422(client):
    header, _uid = _register_and_login(client, "fbk_forge")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(
            "manifest.json",
            json.dumps({"format": "mathmaster-backup", "version": 1}),
        )
    resp = client.post(
        "/api/questions/import/full",
        headers=header,
        files={"file": ("forged.zip", buffer.getvalue(), "application/zip")},
    )
    assert resp.status_code == 422


def test_over_limit_413(client, monkeypatch):
    """超限 413：monkeypatch 上限免造大文件。"""
    header, _uid = _register_and_login(client, "fbk_cap")
    monkeypatch.setattr(questions_router, "_MAX_FULL_BACKUP_BYTES", 10)
    resp = client.post(
        "/api/questions/import/full",
        headers=header,
        files={"file": ("big.zip", b"x" * 64, "application/zip")},
    )
    assert resp.status_code == 413


def test_route_order_not_swallowed(client):
    """路由序防吞噬：GET /export/full 命中新路由（200+zip），而非被
    /{question_id} 当 int 参数捕获（否则 422）。"""
    header, user_id = _register_and_login(client, "fbk_order")
    _seed_history_with_image(user_id)
    resp = client.get("/api/questions/export/full", headers=header)
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"] == "application/zip"
