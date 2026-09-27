"""班级多租户（Batch 10.5）测试：CRUD、成员管理、教师可见范围收紧。"""
from __future__ import annotations

import uuid

import pytest

from backend.database import SessionLocal, init_db
from backend.models.orm import User
from backend.services.class_service import ClassService
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
def students(teacher) -> list[User]:
    with SessionLocal() as session:
        made = []
        for _ in range(2):
            user = User(
                username=f"s_{uuid.uuid4().hex[:8]}", password_hash="x", role="student"
            )
            session.add(user)
            made.append(user)
        session.commit()
        for user in made:
            session.refresh(user)
        return made


class TestClassService:
    def test_create_and_list(self, teacher):
        service = ClassService()
        klass = service.create_class(teacher.id, "高三一班")
        listed = service.list_for_teacher(teacher.id)
        assert any(c["id"] == klass["id"] and c["name"] == "高三一班" for c in listed)

    def test_empty_name_rejected(self, teacher):
        with pytest.raises(ValueError):
            ClassService().create_class(teacher.id, "   ")

    def test_add_remove_student(self, teacher, students):
        service = ClassService()
        klass = service.create_class(teacher.id, "班级A")
        service.add_student(teacher.id, klass["id"], students[0].id)
        assert service.student_ids_for_teacher(teacher.id) == [students[0].id]

        service.add_student(teacher.id, klass["id"], students[0].id)  # 幂等
        assert service.student_ids_for_teacher(teacher.id) == [students[0].id]

        assert service.remove_student(teacher.id, klass["id"], students[0].id) is True
        assert service.student_ids_for_teacher(teacher.id) == []

    def test_cannot_add_non_student(self, teacher, students):
        service = ClassService()
        klass = service.create_class(teacher.id, "班级B")
        other_teacher = teacher
        with pytest.raises(ValueError):
            service.add_student(other_teacher.id, klass["id"], 99999999)

    def test_other_teacher_cannot_operate(self, teacher, students):
        service = ClassService()
        klass = service.create_class(teacher.id, "班级C")
        with SessionLocal() as session:
            stranger = User(
                username=f"t2_{uuid.uuid4().hex[:8]}", password_hash="x", role="teacher"
            )
            session.add(stranger)
            session.commit()
            stranger_id = stranger.id
        with pytest.raises(ValueError):
            service.add_student(stranger_id, klass["id"], students[0].id)

    def test_delete_class(self, teacher, students):
        service = ClassService()
        klass = service.create_class(teacher.id, "班级D")
        service.add_student(teacher.id, klass["id"], students[0].id)
        assert service.delete_class(teacher.id, klass["id"]) is True
        assert service.student_ids_for_teacher(teacher.id) == []


class TestScopeTightening:
    def test_overview_only_own_class_students(self, teacher, students):
        """教师建班后，学生总览不再覆盖班外学生。"""
        service = QuestionService(session_factory=SessionLocal)
        class_service = ClassService()
        klass = class_service.create_class(teacher.id, " scope 班")
        class_service.add_student(teacher.id, klass["id"], students[0].id)

        service.create_manual_question(students[0].id, content_markdown="班内题")
        service.create_manual_question(students[1].id, content_markdown="班外题")

        overview = service.students_overview(teacher.id)
        usernames = {row["username"] for row in overview}
        assert students[0].username in usernames
        assert students[1].username not in usernames

    def test_no_class_teacher_sees_all_students(self, teacher, students):
        """未建班教师保持旧行为：可见全部学生（向后兼容）。"""
        service = QuestionService(session_factory=SessionLocal)
        service.create_manual_question(students[0].id, content_markdown="题")
        overview = service.students_overview(teacher.id)
        assert {row["username"] for row in overview} >= {students[0].username}


class TestClassesAPI:
    @pytest.fixture
    def teacher_headers(self, client):
        username = f"cls_t_{uuid.uuid4().hex[:8]}"
        client.post(
            "/api/auth/register",
            json={"username": username, "password": "secret1", "role": "teacher"},
        )
        login = client.post(
            "/api/auth/login", json={"username": username, "password": "secret1"}
        )
        return {"Authorization": f"Bearer {login.json()['access_token']}"}

    @pytest.fixture
    def student_headers(self, client):
        username = f"cls_s_{uuid.uuid4().hex[:8]}"
        client.post(
            "/api/auth/register",
            json={"username": username, "password": "secret1", "role": "student"},
        )
        login = client.post(
            "/api/auth/login", json={"username": username, "password": "secret1"}
        )
        body = login.json()
        return {
            "headers": {"Authorization": f"Bearer {body['access_token']}"},
            "user_id": body["user_id"],
        }

    def test_class_crud_and_members(self, client, teacher_headers, student_headers):
        created = client.post(
            "/api/classes", headers=teacher_headers, json={"name": "API 班"}
        )
        assert created.status_code == 201, created.text
        class_id = created.json()["id"]

        added = client.post(
            f"/api/classes/{class_id}/members",
            headers=teacher_headers,
            json={"student_id": student_headers["user_id"]},
        )
        assert added.status_code == 204, added.text

        listed = client.get("/api/classes", headers=teacher_headers)
        assert listed.json()[0]["member_count"] == 1

        removed = client.delete(
            f"/api/classes/{class_id}/members/{student_headers['user_id']}",
            headers=teacher_headers,
        )
        assert removed.status_code == 204

        deleted = client.delete(f"/api/classes/{class_id}", headers=teacher_headers)
        assert deleted.status_code == 204

    def test_student_forbidden(self, client, student_headers):
        response = client.post(
            "/api/classes", headers=student_headers["headers"], json={"name": "x"}
        )
        assert response.status_code == 403

    def test_requires_auth(self, client):
        assert client.get("/api/classes").status_code == 401
