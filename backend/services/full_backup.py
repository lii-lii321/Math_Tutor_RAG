"""完整备份 v2（批 G）：zip（manifest.json + images/*）导出与恢复。

manifest 沿用 v1 结构（format / version / questions）并扩展：

- questions 为每题全字段（SM-2 调度状态、星标、笔记、image_hash、
  verification 与 image_ref/image_missing）；
- review_logs 为逐次评分明细（恢复时按 old→new 题目 id 映射挂接）；
- images 为 zip 成员名 → 库内原 image_path（key）的映射；缺失图在题目上
  标 image_missing，不阻断导出。

导入（v2）安全与健壮性约定：

- zip slip 防护：成员名拒绝绝对路径、盘符与 ``..`` 上跳；
- manifest 的 format/version 校验，不符即 ValueError；
- 值域校验逐条跳过并计数，不阻断整批：grade/quality/difficulty 白名单、
  ease 合理区间、ISO 时间戳解析失败即跳过该条；
- 【阻断修正】图片不得按 zip 内原 key 落库——原 key 内嵌原属主 id
  （question_mixins._persist_image 的 ``images/u{user_id}/…`` 约定），
  必须按新属主重新生成 key 并回写 image_path，zip 成员名仅作 manifest
  映射，避免与原用户共享存储对象、被孤儿图清理连坐 404；
- 幂等：image_hash 优先 + 无图题 sha256(content|answer) 指纹比对既有题集，
  命中即整题（含日志）跳过，重复导入不翻倍；
- 导入后逐题 _reindex_owned 同步向量库（失败降级不阻断）。

v1 JSON 契约（export_user_data / import_user_data 与 API 端点）零改动。
"""
from __future__ import annotations

import datetime as dt
import hashlib
import io
import json
import uuid
import zipfile
from decimal import Decimal
from pathlib import Path, PurePosixPath

from backend.database import session_scope
from backend.models.orm import Question, ReviewLog
from backend.utils.logging import get_logger

logger = get_logger("full_backup")

FULL_BACKUP_FORMAT = "mathmaster-full-backup"
FULL_BACKUP_VERSION = 2
_MANIFEST_NAME = "manifest.json"
_IMAGE_DIR = "images"

_VALID_GRADES = frozenset({"again", "hard", "good", "easy"})  # orm ReviewLog.grade 注释
_VALID_QUALITIES = frozenset({0, 3, 4, 5})  # orm ReviewLog.quality：SM-2 q
_VALID_DIFFICULTIES = frozenset({"easy", "medium", "hard"})  # 与 create_manual_question 同源
_VALID_IMAGE_SUFFIXES = frozenset({".jpg", ".jpeg", ".png", ".webp"})
# SM-2 ease 合理区间（调度器初始 2.5，上下修有限）
_MIN_EASE, _MAX_EASE = 1.0, 5.0


class _SkipItem(Exception):
    """单条数据非法：跳过并计数，不阻断整批。"""


def _iso(value: dt.datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _parse_iso(value, *, field: str) -> dt.datetime | None:
    """ISO 时间戳解析；失败按该条数据非法处理（跳过该条）。"""
    if value is None or value == "":
        return None
    try:
        parsed = dt.datetime.fromisoformat(str(value))
    except ValueError as exc:
        raise _SkipItem(f"时间戳 {field} 无法解析: {value!r}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed


def _fingerprint(content_markdown: str, answer: str) -> str:
    """无图题的幂等指纹：sha256(content|answer)。"""
    return hashlib.sha256(f"{content_markdown}|{answer}".encode()).hexdigest()


def _safe_member_name(name: str) -> None:
    """zip slip 防护：拒绝绝对路径、Windows 盘符与 ``..`` 上跳成员。"""
    normalized = name.replace("\\", "/")
    posix = PurePosixPath(normalized)
    if posix.is_absolute() or ".." in posix.parts or ":" in normalized.split("/")[0]:
        raise ValueError(f"备份包含不安全的路径成员: {name!r}")


def _new_image_key(user_id: int, member_name: str) -> str:
    """按新属主生成存储 key（与 _persist_image 同型；成员名仅取后缀）。"""
    suffix = PurePosixPath(member_name.replace("\\", "/")).suffix.lower()
    if suffix not in _VALID_IMAGE_SUFFIXES:
        suffix = ".jpg"
    return (
        f"images/u{user_id}/"
        f"{dt.datetime.now():%Y%m%d_%H%M%S}_{uuid.uuid4().hex[:8]}{suffix}"
    )


# ---------- 导出 ----------


def _question_to_manifest(question: Question, storage) -> tuple[dict, list[tuple[str, bytes]]]:
    """一道题 → manifest 条目（全字段）+ zip 图片成员（缺失不阻断）。"""
    image_ref = None
    image_missing = False
    blobs: list[tuple[str, bytes]] = []
    key = question.image_path.replace("\\", "/") if question.image_path else None
    if key:
        try:
            data = storage.load(key)
        except Exception:  # noqa: BLE001 - 缺失图标记 missing，不阻断导出
            image_missing = True
        else:
            suffix = Path(key).suffix or ".jpg"
            image_ref = f"{_IMAGE_DIR}/q{question.id}{suffix}"
            blobs.append((image_ref, data))
    return {
        "id": question.id,  # 原 id，仅作日志挂接映射，导入不保留
        "content_markdown": question.content_markdown,
        "answer": question.answer or "",
        "knowledge_points": list(question.knowledge_points or []),
        "tags": list(question.tags or []),
        "difficulty": question.difficulty,
        "followup_question": question.followup_question or "",
        "source": question.source,
        "user_note": question.user_note,
        "ocr_text": question.ocr_text,
        "image_hash": question.image_hash,
        "starred": bool(question.starred),
        "reps": int(question.reps or 0),
        "ease": float(question.ease or 0),
        "interval_days": float(question.interval_days or 0),
        "due_at": _iso(question.due_at),
        "last_reviewed_at": _iso(question.last_reviewed_at),
        "created_at": _iso(question.created_at),
        "verification": {
            "status": question.verification_status,
            "confidence": question.verification_confidence,
            "methods": list(question.verification_methods or []),
            "verified_at": _iso(question.verified_at),
        },
        "image_key": key,  # 仅参考，导入不复用（原 key 内嵌原属主 id）
        "image_ref": image_ref,
        "image_missing": image_missing,
    }, blobs


def _log_to_manifest(log: ReviewLog) -> dict:
    return {
        "question_id": log.question_id,
        "grade": log.grade,
        "quality": int(log.quality),
        "prev_interval": float(log.prev_interval or 0),
        "next_interval": float(log.next_interval or 0),
        "ease_after": float(log.ease_after or 0),
        "reviewed_at": _iso(log.reviewed_at),
    }


def export_full_backup(user_id: int) -> io.BytesIO:
    """导出完整备份 zip（题目全字段 + 原图 + 复习日志），缺失图不阻断。"""
    from backend.services.storage import get_storage

    storage = get_storage()
    with session_scope() as session:
        questions = (
            session.query(Question)
            .filter_by(user_id=user_id)
            .order_by(Question.id)
            .all()
        )
        logs = (
            session.query(ReviewLog)
            .filter_by(user_id=user_id)
            .order_by(ReviewLog.id)
            .all()
        )
        manifest_questions: list[dict] = []
        blobs: list[tuple[str, bytes]] = []
        for question in questions:
            entry, question_blobs = _question_to_manifest(question, storage)
            manifest_questions.append(entry)
            blobs.extend(question_blobs)
        manifest_logs = [_log_to_manifest(log) for log in logs]

    manifest = {
        "format": FULL_BACKUP_FORMAT,
        "version": FULL_BACKUP_VERSION,
        "exported_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "count": len(manifest_questions),
        "questions": manifest_questions,
        "review_logs": manifest_logs,
        "images": {member: None for member, _ in blobs},  # 成员名登记；原 key 见题目 image_key
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(_MANIFEST_NAME, json.dumps(manifest, ensure_ascii=False, indent=2))
        for member, data in blobs:
            archive.writestr(member, data)
    buffer.seek(0)
    return buffer


# ---------- 导入 ----------


def _require_number(item: dict, field: str, default=None, *, cast=float):
    raw = item.get(field, default)
    if raw is None:
        return default
    try:
        return cast(raw)
    except (TypeError, ValueError) as exc:
        raise _SkipItem(f"{field} 非法: {raw!r}") from exc


def _question_from_manifest(item: dict, user_id: int, image_path: str | None) -> Question:
    """manifest 条目 → ORM Question（全字段恢复 + 值域校验，非法抛 _SkipItem）。"""
    content = str(item.get("content_markdown", "") or "").strip()
    if not content:
        raise _SkipItem("题目内容为空")
    difficulty = str(item.get("difficulty") or "medium")
    if difficulty not in _VALID_DIFFICULTIES:
        raise _SkipItem(f"difficulty 非法: {difficulty!r}")
    ease = _require_number(item, "ease", 2.5)
    if not _MIN_EASE <= ease <= _MAX_EASE:
        raise _SkipItem(f"ease 超出合理区间: {ease!r}")
    verification = item.get("verification") or {}
    try:
        verified_at = _parse_iso(verification.get("verified_at"), field="verified_at")
    except _SkipItem:
        verified_at = None  # 验证时间戳坏了仅丢弃该子字段，不放弃整题
    return Question(
        user_id=user_id,
        content_markdown=content,
        answer=str(item.get("answer", "") or ""),
        knowledge_points=[str(t) for t in (item.get("knowledge_points") or [])][:8],
        tags=[str(t) for t in (item.get("tags") or [])][:8],
        difficulty=difficulty,
        followup_question=str(item.get("followup_question", "") or "") or None,
        image_path=image_path,
        source="imported",
        ocr_text=item.get("ocr_text"),
        image_hash=str(item["image_hash"]) if item.get("image_hash") else None,
        verification_status=verification.get("status"),
        verification_confidence=verification.get("confidence"),
        verification_methods=list(verification.get("methods") or []),
        verified_at=verified_at,
        starred=bool(item.get("starred", False)),
        user_note=(str(item.get("user_note")) if item.get("user_note") else None),
        reps=int(_require_number(item, "reps", 0, cast=float)),
        ease=ease,
        interval_days=_require_number(item, "interval_days", 0.0),
        due_at=_parse_iso(item.get("due_at"), field="due_at"),
        last_reviewed_at=_parse_iso(item.get("last_reviewed_at"), field="last_reviewed_at"),
        created_at=_parse_iso(item.get("created_at"), field="created_at")
        or dt.datetime.now(dt.timezone.utc),
    )


def _log_from_manifest(item: dict, user_id: int, question_id: int) -> ReviewLog:
    """manifest 日志条目 → ORM ReviewLog（值域校验 + float ease→Decimal）。"""
    grade = str(item.get("grade") or "")
    if grade not in _VALID_GRADES:
        raise _SkipItem(f"grade 非法: {grade!r}")
    try:
        quality = int(item.get("quality"))
    except (TypeError, ValueError) as exc:
        raise _SkipItem(f"quality 非法: {item.get('quality')!r}") from exc
    if quality not in _VALID_QUALITIES:
        raise _SkipItem(f"quality 非法: {quality!r}")
    return ReviewLog(
        question_id=question_id,
        user_id=user_id,
        grade=grade,
        quality=quality,
        prev_interval=_require_number(item, "prev_interval", 0.0),
        next_interval=_require_number(item, "next_interval", 0.0),
        ease_after=Decimal(str(_require_number(item, "ease_after", 0.0))),
        reviewed_at=_parse_iso(item.get("reviewed_at"), field="reviewed_at")
        or dt.datetime.now(dt.timezone.utc),
    )


def import_full_backup(user_id: int, payload: bytes) -> dict:
    """从完整备份 zip 恢复（题目 + 新属主图片 + 复习日志），返回计数。

    返回 ``{"questions", "logs", "images", "missing_images", "skipped"}``。
    """
    try:
        archive = zipfile.ZipFile(io.BytesIO(payload))
    except zipfile.BadZipFile as exc:
        raise ValueError("备份文件不是有效的 zip") from exc

    id_map: dict[int, int] = {}
    imported_questions = 0
    imported_images = 0
    missing_images = 0
    skipped = 0
    try:
        with archive:
            for name in archive.namelist():
                _safe_member_name(name)
            if _MANIFEST_NAME not in archive.namelist():
                raise ValueError("备份包缺少 manifest.json")
            try:
                manifest = json.loads(archive.read(_MANIFEST_NAME).decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ValueError("manifest.json 不是有效的 JSON") from exc
            if manifest.get("format") != FULL_BACKUP_FORMAT:
                raise ValueError("备份包格式不正确（需要完整备份 zip）")
            if manifest.get("version") != FULL_BACKUP_VERSION:
                raise ValueError(f"不支持的备份包版本: {manifest.get('version')!r}")
            items = manifest.get("questions")
            if not isinstance(items, list):
                raise ValueError("备份包缺少 questions 列表")

            with session_scope() as session:
                existing_rows = (
                    session.query(Question).filter_by(user_id=user_id).all()
                )
            existing_hashes = {q.image_hash for q in existing_rows if q.image_hash}
            existing_fingerprints = {
                _fingerprint(q.content_markdown, q.answer or "") for q in existing_rows
            }

            from backend.services.storage import get_storage

            storage = get_storage()
            for item in items:
                try:
                    image_hash = str(item["image_hash"]) if item.get("image_hash") else None
                    content = str(item.get("content_markdown", "") or "").strip()
                    answer = str(item.get("answer", "") or "")
                    if image_hash and image_hash in existing_hashes:
                        continue  # 幂等：同图整题（含日志）跳过
                    if (
                        not image_hash
                        and content
                        and _fingerprint(content, answer) in existing_fingerprints
                    ):
                        continue
                    image_path = None
                    image_ref = item.get("image_ref")
                    if image_ref:
                        _safe_member_name(str(image_ref))
                        try:
                            data = archive.read(str(image_ref))
                        except KeyError:
                            missing_images += 1  # 包内缺成员：题目照常恢复，无图
                        else:
                            image_path = _new_image_key(user_id, str(image_ref))
                            storage.save(image_path, data)
                            imported_images += 1
                    question = _question_from_manifest(item, user_id, image_path)
                    with session_scope() as session:
                        session.add(question)
                        session.flush()
                        new_id = question.id
                    if item.get("id") is not None:
                        id_map[int(item["id"])] = new_id
                    if image_hash:
                        existing_hashes.add(image_hash)
                    existing_fingerprints.add(_fingerprint(content, answer))
                    imported_questions += 1
                except _SkipItem as exc:
                    logger.warning("完整备份跳过一条题目: %s", exc)
                    skipped += 1
                except Exception as exc:  # noqa: BLE001 - 单条失败不阻断整体
                    logger.warning("完整备份导入单条题目失败: %s", exc)
                    skipped += 1

            imported_logs = 0
            for log_item in manifest.get("review_logs") or []:
                try:
                    old_qid = log_item.get("question_id")
                    new_qid = id_map.get(int(old_qid)) if old_qid is not None else None
                    if new_qid is None:
                        # 题目未新导入（去重跳过/无效），其日志此前已随题恢复，跳过防翻倍
                        continue
                    log = _log_from_manifest(log_item, user_id, new_qid)
                    with session_scope() as session:
                        session.add(log)
                    imported_logs += 1
                except (_SkipItem, TypeError, ValueError) as exc:
                    logger.warning("完整备份跳过一条复习日志: %s", exc)
                    skipped += 1
    finally:
        archive.close()

    # 向量索引同步：逐题 _reindex_owned，失败降级不阻断
    if id_map:
        from backend.services.question_service import QuestionService

        service = QuestionService()
        for new_id in id_map.values():
            try:
                with session_scope() as session:
                    question = session.get(Question, new_id)
                    if question is not None:
                        service._reindex_owned(question)
            except Exception as exc:  # noqa: BLE001 - 索引失败降级
                logger.warning("完整备份重建向量索引失败 question=%s: %s", new_id, exc)

    logger.info(
        "完整备份导入 user=%s：题目 %s / 日志 %s / 图片 %s（缺失 %s，跳过 %s）",
        user_id,
        imported_questions,
        imported_logs,
        imported_images,
        missing_images,
        skipped,
    )
    return {
        "questions": imported_questions,
        "logs": imported_logs,
        "images": imported_images,
        "missing_images": missing_images,
        "skipped": skipped,
    }
