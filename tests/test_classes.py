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

    def test_class_student_ids_scoped(self, teacher, students):
        """class_student_ids 只返回该班成员；他人班级返回空。"""
        service = ClassService()
        klass = service.create_class(teacher.id, "范围班")
        service.add_student(teacher.id, klass["id"], students[0].id)
        assert service.class_student_ids(teacher.id, klass["id"]) == [students[0].id]
        assert service.class_student_ids(teacher.id, klass["id"] + 999) == []

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

    def test_keyword_search_scoped_after_class_created(self, teacher, students):
        """教师建班后，关键词检索（SQL 路）与语义路同口径：不再覆盖班外学生。

        审计 D1 回归：修复前 SQL 路对 include_others 教师无任何 user 过滤，
        建班教师关键词搜索仍能看到班外学生题目。
        """
        service = QuestionService(session_factory=SessionLocal)
        class_service = ClassService()
        klass = class_service.create_class(teacher.id, " 检索 scope 班")
        class_service.add_student(teacher.id, klass["id"], students[0].id)

        service.create_manual_question(
            students[0].id, content_markdown="班内勾股定理题 a²+b²=c²"
        )
        service.create_manual_question(
            students[1].id, content_markdown="班外勾股定理题直角三角形"
        )

        hits = service.list_questions(
            teacher.id, include_others=True, keyword="勾股定理", semantic=False
        )
        assert {q.user_id for q in hits} <= {students[0].id, teacher.id}
        assert students[1].id not in {q.user_id for q in hits}

        # X-Total-Count 与列表同口径
        total = service.count_for_user(teacher.id, include_others=True, keyword="勾股定理")
        assert total == len(hits)

        # 语义开启的混合路同样不得回流班外题
        hybrid = service.list_questions(
            teacher.id, include_others=True, keyword="勾股定理", semantic=True
        )
        assert students[1].id not in {q.user_id for q in hybrid}

    def test_no_class_teacher_sees_only_own_questions(self, teacher, students):
        """范围收口（2026-10-25）：未建班教师不再回退全部学生——只看自己的题。"""
        service = QuestionService(session_factory=SessionLocal)
        marker = "无班收口题"
        service.create_manual_question(students[0].id, content_markdown=marker)
        service.create_manual_question(students[1].id, content_markdown=marker)
        service.create_manual_question(teacher.id, content_markdown=f"自己的{marker}")

        hits = service.list_questions(
            teacher.id, include_others=True, keyword="无班收口", semantic=False
        )
        assert {q.user_id for q in hits} == {teacher.id}

        # 语义混合路与计数同口径
        hybrid = service.list_questions(
            teacher.id, include_others=True, keyword="无班收口", semantic=True
        )
        assert {q.user_id for q in hybrid} <= {teacher.id}
        assert service.count_for_user(teacher.id, include_others=True, keyword="无班收口") == 1

    def test_class_with_zero_members_sees_only_own(self, teacher, students):
        """建班后零成员：范围 = 自己 + 成员（空），不回退全量（原实现的漏网分支）。"""
        service = QuestionService(session_factory=SessionLocal)
        ClassService().create_class(teacher.id, "空成员班")
        service.create_manual_question(students[0].id, content_markdown="空成员班外题 zero_members_probe")

        hits = service.list_questions(
            teacher.id, include_others=True, keyword="zero_members_probe", semantic=False
        )
        assert hits == []

    def test_dashboard_stats_scoped_after_class_created(self, teacher, students):
        """教师建班后，看板统计（提升项 #6）与学生总览/检索同口径：只算班内。"""
        service = QuestionService(session_factory=SessionLocal)
        class_service = ClassService()
        klass = class_service.create_class(teacher.id, " 看板 scope 班")
        class_service.add_student(teacher.id, klass["id"], students[0].id)

        service.create_manual_question(students[0].id, content_markdown="班内看板题")
        service.create_manual_question(students[1].id, content_markdown="班外看板题")

        stats = service.dashboard_stats(teacher.id, include_others=True)
        assert stats["total"] == 1
        # 复习池/掌握归档本来就只算自己名下，班外题不得进入 total 口径
        assert stats["due"] == 0

    def test_no_class_teacher_overview_is_empty(self, teacher, students):
        """范围收口：未建班教师的学生总览为空（界面引导建班），不回退全量。"""
        service = QuestionService(session_factory=SessionLocal)
        service.create_manual_question(students[0].id, content_markdown="题")
        overview = service.students_overview(teacher.id)
        assert overview == []


class TestClassesAPI:
    @pytest.fixture
    def teacher_headers(self, client):
        username = f"cls_t_{uuid.uuid4().hex[:8]}"
        client.post(
            "/api/auth/register",
            json={
                "username": username,
                "password": "secret1",
                "role": "teacher",
                "invite_code": "test-invite-code",
            },
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
