"""Sprint A P0 回归测试：教师邀请码、验证器 uncertain 聚合、备份导入幂等。"""
from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from backend.database import SessionLocal, init_db
from backend.models.orm import User
from backend.services.auth import AuthService


@pytest.fixture
def db():
    init_db(seed_users=True)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


class TestTeacherInvite:
    def _register(self, db, monkeypatch, invite_code: str, invite_env: str):
        from backend.models.schemas import RegisterInput
        from backend.services import auth as auth_module

        stub = SimpleNamespace(
            teacher_invite_code=invite_env, bcrypt_rounds=4
        )
        monkeypatch.setattr(auth_module, "get_settings", lambda: stub)
        payload = RegisterInput(
            username=f"ti_{uuid.uuid4().hex[:8]}",
            password="secret1",
            role="teacher",
            invite_code=invite_code,
        )
        return AuthService(db).register(payload)

    def test_invite_disabled_rejects_teacher(self, db, monkeypatch):
        result = self._register(db, monkeypatch, invite_code="whatever", invite_env="")
        assert result.ok is False
        assert "已关闭" in result.message

    def test_wrong_code_rejected(self, db, monkeypatch):
        result = self._register(db, monkeypatch, invite_code="wrong", invite_env="right")
        assert result.ok is False
        assert "邀请码不正确" in result.message

    def test_correct_code_accepted(self, db, monkeypatch):
        result = self._register(db, monkeypatch, invite_code="right", invite_env="right")
        assert result.ok is True
        assert result.role == "teacher"

    def test_student_needs_no_invite(self, db, monkeypatch):
        """学生注册不受邀请码影响（含邀请码关闭时）。"""
        from backend.models.schemas import RegisterInput
        from backend.services import auth as auth_module

        stub = SimpleNamespace(teacher_invite_code="", bcrypt_rounds=4)
        monkeypatch.setattr(auth_module, "get_settings", lambda: stub)
        payload = RegisterInput(
            username=f"ti_s_{uuid.uuid4().hex[:8]}", password="secret1", role="student"
        )
        result = AuthService(db).register(payload)
        assert result.ok is True


class TestTeacherInviteAPI:
    def test_api_teacher_without_invite_rejected(self, client):
        username = f"noinv_{uuid.uuid4().hex[:8]}"
        response = client.post(
            "/api/auth/register",
            json={"username": username, "password": "secret1", "role": "teacher"},
        )
        assert response.status_code == 409
        assert "邀请码" in response.json()["detail"] or "已关闭" in response.json()["detail"]

    def test_api_teacher_with_invite_accepted(self, client):
        username = f"winv_{uuid.uuid4().hex[:8]}"
        created = client.post(
            "/api/auth/register",
            json={
                "username": username,
                "password": "secret1",
                "role": "teacher",
                "invite_code": "test-invite-code",
            },
        )
        assert created.status_code == 201
        assert created.json()["role"] == "teacher"


class TestVerifierUncertainAggregation:
    def test_uncertain_only_keeps_methods_and_details(self, client, monkeypatch):
        """仅 uncertain 时不再抛 StopIteration 丢证明（回归：methods 必须保留）。"""
        import sympy

        from backend.services.math_verifier.answer_verifier import verify_answer

        def _fake_simplify(_expr):
            return sympy.Integer(1)  # 化简永远"不一致"

        monkeypatch.setattr(sympy, "simplify", _fake_simplify)
        result = verify_answer("求 $f(x) = x^2$ 的导数", "", "导数为 $f'(x) = 2x$")
        assert result.status == "uncertain"
        assert result.methods == ["derivative_inverse"], "uncertain 聚合必须保留验证明细"
        assert 0 < result.confidence <= 1


class TestImportIdempotency:
    def test_reimport_same_backup_skips_hash_duplicates(self, client):
        import uuid as _uuid

        from backend.database import SessionLocal
        from backend.services.question_service import QuestionService

        username = f"imp_{_uuid.uuid4().hex[:8]}"
        with SessionLocal() as session:
            user = User(username=username, password_hash="x", role="student")
            session.add(user)
            session.commit()
            session.refresh(user)

        service = QuestionService(session_factory=SessionLocal)
        service.create_manual_question(
            user.id, content_markdown="幂等导入题", image_hash="deadbeef" * 4
        )
        backup = service.export_user_data(user.id)

        first = service.import_user_data(user.id, backup)
        assert first == 0, "同用户重导入应全部按哈希跳过"

        total = len(service.list_questions(user.id, semantic=False))
        assert total == 1

    def test_cross_user_import_then_reimport(self, client):
        import uuid as _uuid

        from backend.database import SessionLocal
        from backend.services.question_service import QuestionService

        owner = f"imp_o_{_uuid.uuid4().hex[:8]}"
        target = f"imp_t_{_uuid.uuid4().hex[:8]}"
        with SessionLocal() as session:
            u1 = User(username=owner, password_hash="x", role="student")
            u2 = User(username=target, password_hash="x", role="student")
            session.add_all([u1, u2])
            session.commit()
            session.refresh(u1)
            session.refresh(u2)

        service = QuestionService(session_factory=SessionLocal)
        service.create_manual_question(
            u1.id, content_markdown="跨用户导入题", image_hash="cafebabe" * 4
        )
        backup = service.export_user_data(u1.id)

        first = service.import_user_data(u2.id, backup)
        assert first == 1
        again = service.import_user_data(u2.id, backup)
        assert again == 0, "第二次导入必须幂等跳过"
        assert len(service.list_questions(u2.id, semantic=False)) == 1
