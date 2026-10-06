"""完整备份 v2（批 G）服务层测试：zip 往返 / 图片新属主 key / 幂等 / 安全。

全程零 AI 网络调用（analyze_and_save 走 MockProvider）；图片经测试专用
DATA_DIR 的 local 存储后端读写，互不串扰。
"""
from __future__ import annotations

import io
import json
import uuid
import zipfile

import pytest
from PIL import Image

from backend.config import get_settings
from backend.database import SessionLocal, session_scope
from backend.models.orm import Question, ReviewLog, User
from backend.services.full_backup import (
    export_full_backup,
    import_full_backup,
)
from backend.services.question_service import QuestionService
from backend.services.storage import get_storage


def _tiny_jpeg() -> bytes:
    image = Image.new("RGB", (10, 10), (200, 90, 60))
    stream = io.BytesIO()
    image.save(stream, format="JPEG")
    return stream.getvalue()


@pytest.fixture
def service():
    return QuestionService(session_factory=SessionLocal)


@pytest.fixture
def owner(db_session):
    user = User(username=f"fbk_a_{uuid.uuid4().hex[:8]}", password_hash="x", role="student")
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def receiver(db_session):
    user = User(username=f"fbk_b_{uuid.uuid4().hex[:8]}", password_hash="x", role="student")
    db_session.add(user)
    db_session.commit()
    return user


def _seed_full_history(service, user_id: int) -> int:
    """大满贯素材：带图题 + 难度 hard + 星标 + 笔记 + 评分 3 次，返回题目 id。"""
    out, _analysis = service.analyze_and_save(user_id, _tiny_jpeg(), user_tags=["备份"])
    qid = out.id
    service.set_difficulty_many([qid], user_id, "hard")
    assert service.toggle_star(qid, user_id) is True
    service.update_question(
        qid, user_id, content_markdown=None, answer=None, tags=None,
        knowledge_points=None, user_note="易错：判别式符号",
    )
    for grade in ("again", "good", "easy"):
        assert service.grade_review(qid, user_id, grade) is not None
    return qid


def _orm_question(user_id: int) -> dict:
    """会话内取值快照（避免 detached 对象跨会话访问失效）。"""
    with session_scope() as session:
        q = session.query(Question).filter_by(user_id=user_id).one()
        return {
            "content_markdown": q.content_markdown,
            "difficulty": q.difficulty,
            "starred": bool(q.starred),
            "user_note": q.user_note,
            "reps": int(q.reps or 0),
            "ease": float(q.ease or 0),
            "interval_days": float(q.interval_days or 0),
            "due_at": q.due_at,
            "last_reviewed_at": q.last_reviewed_at,
            "image_hash": q.image_hash,
            "image_path": q.image_path,
        }


def _orm_log_count(user_id: int) -> int:
    with session_scope() as session:
        return len(session.query(ReviewLog).filter_by(user_id=user_id).all())


def test_full_backup_roundtrip_restores_sm2_state(service, owner, receiver):
    """大满贯往返：SM-2 进度/星标/笔记/难度/日志条数逐项一致。"""
    _seed_full_history(service, owner.id)
    original = _orm_question(owner.id)
    original_logs = _orm_log_count(owner.id)
    assert original_logs == 3

    payload = export_full_backup(owner.id).getvalue()
    result = import_full_backup(receiver.id, payload)

    assert result["questions"] == 1
    assert result["logs"] == 3
    assert result["images"] == 1
    assert result["missing_images"] == 0

    restored = _orm_question(receiver.id)
    assert restored["content_markdown"] == original["content_markdown"]
    assert restored["difficulty"] == "hard"
    assert restored["starred"] is True
    assert restored["user_note"] == "易错：判别式符号"
    assert restored["reps"] == original["reps"]
    assert restored["ease"] == original["ease"]
    assert restored["interval_days"] == original["interval_days"]
    assert restored["due_at"] is not None and original["due_at"] is not None
    assert restored["due_at"] == original["due_at"]
    assert restored["last_reviewed_at"] == original["last_reviewed_at"]
    assert restored["image_hash"] == original["image_hash"]
    assert _orm_log_count(receiver.id) == 3


def test_copy_image_uses_new_owner_key_and_survives_original_delete(service, owner, receiver):
    """【阻断修正】副本图按新属主 key 重建：删除原用户存储对象后副本仍可读。"""
    _seed_full_history(service, owner.id)
    original = _orm_question(owner.id)
    payload = export_full_backup(owner.id).getvalue()
    import_full_backup(receiver.id, payload)

    restored = _orm_question(receiver.id)
    assert restored["image_path"]
    assert restored["image_path"] != original["image_path"], "不得复用内嵌原属主 id 的旧 key"
    assert f"/u{owner.id}/" not in restored["image_path"].replace("\\", "/")

    storage = get_storage()
    assert storage.exists(original["image_path"])
    original_bytes = storage.load(original["image_path"])
    # 删除原用户的存储对象（模拟孤儿图清理/原用户删题）
    (get_settings().data_dir / original["image_path"]).unlink()
    assert not storage.exists(original["image_path"])
    assert storage.exists(restored["image_path"])
    assert storage.load(restored["image_path"]) == original_bytes


def test_v1_json_backup_still_importable(service, owner):
    """v1 JSON 契约回归钉：export_user_data/import_user_data 不受 v2 影响。"""
    service.create_manual_question(
        owner.id, content_markdown="v1 兼容题：解方程 $x=1$", answer="x=1", tags=["v1"]
    )
    backup = service.export_user_data(owner.id)
    fresh = User(username=f"fbk_v1_{uuid.uuid4().hex[:8]}", password_hash="x", role="student")
    with session_scope() as session:
        session.add(fresh)
        session.commit()
        fresh_id = fresh.id
    imported = service.import_user_data(fresh_id, backup)
    assert imported == 1
    restored = service.list_questions(fresh_id, semantic=False)[0]
    assert restored.source == "imported"


def test_duplicate_import_is_idempotent(service, owner, receiver):
    _seed_full_history(service, owner.id)
    payload = export_full_backup(owner.id).getvalue()
    first = import_full_backup(receiver.id, payload)
    assert first["questions"] == 1
    second = import_full_backup(receiver.id, payload)
    assert second["questions"] == 0
    assert second["logs"] == 0
    with session_scope() as session:
        assert len(session.query(Question).filter_by(user_id=receiver.id).all()) == 1
        assert len(session.query(ReviewLog).filter_by(user_id=receiver.id).all()) == 3


def test_corrupt_zip_raises_value_error(owner):
    with pytest.raises(ValueError):
        import_full_backup(owner.id, b"this is not a zip")


def test_forged_manifest_rejected(owner):
    """format/version 不符（含把 v1 JSON 塞进 zip）明确 ValueError。"""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("manifest.json", json.dumps({"format": "mathmaster-backup", "version": 1}))
    with pytest.raises(ValueError):
        import_full_backup(owner.id, buffer.getvalue())

    buffer2 = io.BytesIO()
    with zipfile.ZipFile(buffer2, "w") as archive:
        archive.writestr(
            "manifest.json",
            json.dumps({"format": "mathmaster-full-backup", "version": 99, "questions": []}),
        )
    with pytest.raises(ValueError):
        import_full_backup(owner.id, buffer2.getvalue())


def test_zip_slip_member_rejected(owner):
    buffer = io.BytesIO()
    manifest = {
        "format": "mathmaster-full-backup",
        "version": 2,
        "questions": [],
        "review_logs": [],
    }
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        archive.writestr("../evil.txt", "pwn")
    with pytest.raises(ValueError):
        import_full_backup(owner.id, buffer.getvalue())

    for evil in ("/abs/evil.txt", "C:/evil.txt", "images/../../evil.txt"):
        buffer2 = io.BytesIO()
        with zipfile.ZipFile(buffer2, "w") as archive:
            archive.writestr("manifest.json", json.dumps(manifest))
            archive.writestr(evil, "pwn")
        with pytest.raises(ValueError):
            import_full_backup(owner.id, buffer2.getvalue())


def test_invalid_values_skipped_without_blocking(service, owner, receiver):
    """difficulty/ease/时间戳非法的条目逐条跳过计数，合法条目照常导入。"""
    good = {
        "id": 1,
        "content_markdown": "合法题：$1+1=?$",
        "answer": "2",
        "difficulty": "easy",
        "reps": 1,
        "ease": 2.5,
        "interval_days": 1.0,
        "created_at": "2026-10-01T00:00:00+00:00",
    }
    bad_difficulty = {**good, "id": 2, "content_markdown": "难度非法题", "difficulty": "impossible"}
    bad_ease = {**good, "id": 3, "content_markdown": "ease 非法题", "ease": 9.9}
    bad_ts = {**good, "id": 4, "content_markdown": "时间戳非法题", "due_at": "not-a-date"}
    payload_bytes = io.BytesIO()
    manifest = {
        "format": "mathmaster-full-backup",
        "version": 2,
        "questions": [good, bad_difficulty, bad_ease, bad_ts],
        "review_logs": [
            {"question_id": 1, "grade": "excellent", "quality": 5},  # grade 非法 → 跳过
            {"question_id": 1, "grade": "good", "quality": 4, "ease_after": 2.6},
        ],
    }
    with zipfile.ZipFile(payload_bytes, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest))

    result = import_full_backup(receiver.id, payload_bytes.getvalue())
    assert result["questions"] == 1
    assert result["skipped"] == 4  # 3 题 + 1 日志
    restored = _orm_question(receiver.id)
    assert restored["content_markdown"] == "合法题：$1+1=?$"
    assert _orm_log_count(receiver.id) == 1  # 仅合法日志挂接
