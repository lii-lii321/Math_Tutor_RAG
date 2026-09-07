from __future__ import annotations

from backend.models.schemas import RegisterInput
from backend.services.auth import AuthService


def test_login_success_and_failure(db_session):
    service = AuthService(db_session)
    ok = service.login("demo", "demo123")
    assert ok.ok and ok.username == "demo"

    bad = service.login("demo", "wrong")
    assert not bad.ok


def test_register_validates_and_persists(db_session):
    service = AuthService(db_session)
    payload = RegisterInput(username="new_student", password="abc12345")
    result = service.register(payload)
    assert result.ok

    login = service.login("new_student", "abc12345")
    assert login.ok and login.role == "student"


def test_register_duplicate_username_rejected(db_session):
    service = AuthService(db_session)
    result = service.register(RegisterInput(username="demo", password="abc12345"))
    assert not result.ok


def test_register_rejects_short_password(db_session):
    import pydantic
    import pytest

    with pytest.raises(pydantic.ValidationError):
        RegisterInput(username="someone", password="123")


def test_change_password_flow(db_session):
    service = AuthService(db_session)
    wrong_old = service.change_password(999999, "x", "abcdef")
    assert not wrong_old.ok

    ok = service.change_password(999999, "", "abcdef")
    assert not ok.ok
