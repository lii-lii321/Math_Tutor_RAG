"""批量标签与笔记测试。"""
from __future__ import annotations

import pytest

from backend.database import SessionLocal
from backend.services.question_service import QuestionService


@pytest.fixture
def service():
    return QuestionService(session_factory=SessionLocal)


def test_add_tags_to_many_merges(service, db_session):
    from backend.models.orm import User

    s1 = User(username="batch_s1", password_hash="x", role="student")
    db_session.add(s1)
    db_session.commit()

    first = service.create_manual_question(s1.id, content_markdown="批量一", tags=["a"])
    second = service.create_manual_question(s1.id, content_markdown="批量二", tags=["b"])

    changed = service.add_tags_to_many(
        [first.id, second.id], s1.id, ["批量", "a"]
    )
    assert changed == 2

    updated_first = service.get_question(first.id, s1.id)
    assert updated_first is not None
    assert "批量" in updated_first.tags
    assert "a" in updated_first.tags  # 已有标签不会被重复添加


def test_add_tags_rejects_others_question(service, db_session, student_user):
    from backend.models.orm import User

    saved, _ = service.analyze_and_save(student_user.id, b"\xff\xd8\xff" + b"0" * 16)

    other = User(username="batch_other", password_hash="x", role="student")
    db_session.add(other)
    db_session.commit()

    assert service.add_tags_to_many([saved.id], other.id, ["x"]) == 0


def test_set_difficulty_many(service, db_session):
    from backend.models.orm import User

    user = User(username="batch_diff", password_hash="x", role="student")
    db_session.add(user)
    db_session.commit()

    ids = [
        service.create_manual_question(user.id, content_markdown=f"难度题{i}").id
        for i in range(3)
    ]
    changed = service.set_difficulty_many(ids, user.id, "hard")
    assert changed == 3
    for qid in ids:
        updated = service.get_question(qid, user.id)
        assert updated is not None and updated.difficulty == "hard"

    with pytest.raises(ValueError):
        service.set_difficulty_many(ids, user.id, "super-hard")


def test_set_difficulty_rejects_others_question(service, db_session):
    from backend.models.orm import User

    owner = User(username="batch_diff_own", password_hash="x", role="student")
    other = User(username="batch_diff_other", password_hash="x", role="student")
    db_session.add_all([owner, other])
    db_session.commit()

    saved = service.create_manual_question(owner.id, content_markdown="别人的难度题")
    assert service.set_difficulty_many([saved.id], other.id, "hard") == 0


def test_remove_tag_from_many(service, db_session):
    from backend.models.orm import User

    user = User(username="batch_rm", password_hash="x", role="student")
    db_session.add(user)
    db_session.commit()

    first = service.create_manual_question(
        user.id, content_markdown="移除一", tags=["临时", "保留"], knowledge_points=["临时"]
    )
    second = service.create_manual_question(user.id, content_markdown="移除二", tags=["临时"])

    changed = service.remove_tag_from_many([first.id, second.id], user.id, "临时")
    assert changed == 2

    updated_first = service.get_question(first.id, user.id)
    assert updated_first is not None
    assert "临时" not in updated_first.tags
    assert "保留" in updated_first.tags
    assert "临时" not in (updated_first.knowledge_points or [])  # 知识点同名项同步清理
    updated_second = service.get_question(second.id, user.id)
    assert updated_second is not None and updated_second.tags == []

    with pytest.raises(ValueError):
        service.remove_tag_from_many([first.id], user.id, "   ")


def test_remove_tag_rejects_others_question(service, db_session):
    from backend.models.orm import User

    owner = User(username="batch_rm_own", password_hash="x", role="student")
    other = User(username="batch_rm_other", password_hash="x", role="student")
    db_session.add_all([owner, other])
    db_session.commit()

    saved = service.create_manual_question(owner.id, content_markdown="别人的标签题", tags=["t"])
    assert service.remove_tag_from_many([saved.id], other.id, "t") == 0
