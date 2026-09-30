"""未读红点（批注已读回执）测试：计数口径、回执清零、API 行为。"""
from __future__ import annotations

import uuid

import pytest

from backend.database import SessionLocal, init_db
from backend.models.orm import User
from backend.services.comment_service import CommentService
from backend.services.question_service import QuestionService


@pytest.fixture
def teacher() -> User:
    init_db(seed_users=True)
    with SessionLocal() as session:
        user = User(username=f"t_{uuid.uuid4().hex[:8]}", password_hash="x", role="teacher")
        session.add(user)
        session.commit()
        session.refresh(user)
        return user


@pytest.fixture
def student() -> User:
    with SessionLocal() as session:
        user = User(username=f"s_{uuid.uuid4().hex[:8]}", password_hash="x", role="student")
        session.add(user)
        session.commit()
        session.refresh(user)
        return user


@pytest.fixture
def services() -> tuple[CommentService, QuestionService]:
    return CommentService(), QuestionService(session_factory=SessionLocal)


class TestUnreadCounts:
    def test_teacher_comment_counts_unread(self, teacher, student, services):
        comment_service, question_service = services
        question = question_service.create_manual_question(student.id, content_markdown="题")
        assert comment_service.total_unread(student.id) == 0

        comment_service.add(question.id, teacher.id, "注意第二问", viewer_role="teacher")
        counts = comment_service.unread_counts(student.id, [question.id])
        assert counts == {question.id: 1}
        assert comment_service.total_unread(student.id) == 1

    def test_own_comment_not_counted(self, teacher, student, services):
        comment_service, question_service = services
        question = question_service.create_manual_question(student.id, content_markdown="题")
        comment_service.add(question.id, student.id, "自己的备注")
        assert comment_service.total_unread(student.id) == 0

    def test_mark_read_clears_and_recounts(self, teacher, student, services):
        comment_service, question_service = services
        question = question_service.create_manual_question(student.id, content_markdown="题")
        comment_service.add(question.id, teacher.id, "批语1", viewer_role="teacher")
        comment_service.mark_read(question.id, student.id)
        assert comment_service.total_unread(student.id) == 0

        comment_service.add(question.id, teacher.id, "批语2", viewer_role="teacher")
        assert comment_service.unread_counts(student.id, [question.id]) == {question.id: 1}

    def test_only_own_questions_counted(self, teacher, student, services):
        """教师在他人的题上留批注，不进入我的未读（题目归属过滤）。"""
        comment_service, question_service = services
        with SessionLocal() as session:
            other = User(
                username=f"s2_{uuid.uuid4().hex[:8]}", password_hash="x", role="student"
            )
            session.add(other)
            session.commit()
            session.refresh(other)
            other_id = other.id
        other_question = question_service.create_manual_question(
            other_id, content_markdown="别人的题"
        )
        comment_service.add(other_question.id, teacher.id, "批语", viewer_role="teacher")
        assert comment_service.total_unread(student.id) == 0
        assert comment_service.unread_counts(student.id, [other_question.id]) == {}

    def test_mark_read_idempotent(self, teacher, student, services):
        comment_service, question_service = services
        question = question_service.create_manual_question(student.id, content_markdown="题")
        comment_service.mark_read(question.id, student.id)
        comment_service.mark_read(question.id, student.id)
        assert comment_service.total_unread(student.id) == 0


class TestUnreadAPI:
    @pytest.fixture
    def teacher_headers(self, client):
        username = f"ru_t_{uuid.uuid4().hex[:8]}"
        client.post(
            "/api/auth/register",
            json={
                "username": username,
                "password": "secret1",
                "role": "teacher",
                "invite_code": "test-invite-code",
            },
        )
        login = client.post("/api/auth/login", json={"username": username, "password": "secret1"})
        return {"Authorization": f"Bearer {login.json()['access_token']}"}

    @pytest.fixture
    def student_auth(self, client):
        username = f"ru_s_{uuid.uuid4().hex[:8]}"
        client.post(
            "/api/auth/register",
            json={"username": username, "password": "secret1", "role": "student"},
        )
        login = client.post("/api/auth/login", json={"username": username, "password": "secret1"})
        body = login.json()
        return {
            "headers": {"Authorization": f"Bearer {body['access_token']}"},
            "user_id": body["user_id"],
        }

    def test_unread_flow(self, client, teacher_headers, student_auth):
        created = client.post(
            "/api/questions/text",
            headers=student_auth["headers"],
            json={"content_markdown": "API 未读题", "answer": "42"},
        )
        assert created.status_code == 201, created.text
        question_id = created.json()["id"]

        assert (
            client.get(
                f"/api/questions/{question_id}/comments/unread",
                headers=student_auth["headers"],
            ).json()["unread"]
            == 0
        )

        added = client.post(
            f"/api/questions/{question_id}/comments",
            headers=teacher_headers,
            json={"content": "教师批语"},
        )
        assert added.status_code == 201, added.text

        unread = client.get(
            f"/api/questions/{question_id}/comments/unread",
            headers=student_auth["headers"],
        )
        assert unread.json()["unread"] == 1

        read = client.post(
            f"/api/questions/{question_id}/comments/read",
            headers=student_auth["headers"],
        )
        assert read.status_code == 204
        assert (
            client.get(
                f"/api/questions/{question_id}/comments/unread",
                headers=student_auth["headers"],
            ).json()["unread"]
            == 0
        )

    def test_unread_requires_auth(self, client):
        assert client.get("/api/questions/1/comments/unread").status_code == 401
        assert client.post("/api/questions/1/comments/read").status_code == 401
