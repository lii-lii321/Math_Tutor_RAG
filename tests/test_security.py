from __future__ import annotations

import uuid

import pytest

from backend.utils.security import hash_password, verify_password


def test_hash_and_verify_roundtrip():
    hashed = hash_password("s3cret", rounds=4)
    assert hashed != "s3cret"
    assert verify_password("s3cret", hashed)


def test_wrong_password_rejected():
    hashed = hash_password("s3cret", rounds=4)
    assert not verify_password("nope", hashed)


def test_empty_inputs_rejected():
    with pytest.raises(ValueError):
        hash_password("")
    assert not verify_password("", "whatever")
    assert not verify_password("x", "")


@pytest.fixture
def sec_headers(client):
    username = f"sec_{uuid.uuid4().hex[:10]}"
    client.post(
        "/api/auth/register",
        json={"username": username, "password": "secret1", "role": "student"},
    )
    login = client.post(
        "/api/auth/login", json={"username": username, "password": "secret1"}
    )
    body = login.json()
    return {
        "access": {"Authorization": f"Bearer {body['access_token']}"},
        "refresh": body["refresh_token"],
        "user_id": body["user_id"],
    }


class TestDualTokens:
    def test_login_returns_refresh_token(self, client, sec_headers):
        assert sec_headers["refresh"]
        me = client.get("/api/questions", headers=sec_headers["access"])
        assert me.status_code == 200

    def test_refresh_mints_new_tokens(self, client, sec_headers):
        response = client.post(
            "/api/auth/refresh", json={"refresh_token": sec_headers["refresh"]}
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["access_token"] and body["refresh_token"]
        assert body["user_id"] == sec_headers["user_id"]

        # 新 access 可用
        assert (
            client.get(
                "/api/questions",
                headers={"Authorization": f"Bearer {body['access_token']}"},
            ).status_code
            == 200
        )
        # 新 refresh 可继续刷新
        again = client.post(
            "/api/auth/refresh", json={"refresh_token": body["refresh_token"]}
        )
        assert again.status_code == 200

    def test_access_token_cannot_refresh(self, client, sec_headers):
        access = sec_headers["access"]["Authorization"].removeprefix("Bearer ")
        response = client.post("/api/auth/refresh", json={"refresh_token": access})
        assert response.status_code == 401

    def test_refresh_token_rejected_as_access(self, client, sec_headers):
        response = client.get(
            "/api/questions",
            headers={"Authorization": f"Bearer {sec_headers['refresh']}"},
        )
        assert response.status_code == 401

    def test_garbage_refresh_rejected(self, client):
        response = client.post("/api/auth/refresh", json={"refresh_token": "garbage-token"})
        assert response.status_code == 401


class TestRequestRateLimiter:
    def test_allow_within_limit_then_block(self):
        from backend.utils.request_limiter import RequestRateLimiter

        limiter = RequestRateLimiter(max_requests=3, window_seconds=60)
        assert [limiter.allow("u1") for _ in range(3)] == [True, True, True]
        assert limiter.allow("u1") is False
        assert limiter.remaining("u1") == 0
        assert limiter.allow("u2") is True  # 不同 key 独立计数

    def test_window_expiry_restores_quota(self, monkeypatch):
        from backend.utils import request_limiter as rl

        clock = {"t": 1000.0}
        monkeypatch.setattr(rl.time, "monotonic", lambda: clock["t"])
        limiter = rl.RequestRateLimiter(max_requests=2, window_seconds=60)
        assert limiter.allow("k") and limiter.allow("k") and not limiter.allow("k")
        clock["t"] += 61  # 窗口滑过
        assert limiter.allow("k") is True

    def test_noop_limiter(self):
        from backend.utils.request_limiter import NoopRequestRateLimiter

        limiter = NoopRequestRateLimiter()
        assert all(limiter.allow("k") for _ in range(100))
