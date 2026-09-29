"""令牌吊销生命周期：改密 / 登出递增 token_version，旧令牌 401，新令牌可用。"""
from __future__ import annotations

import datetime as dt

import jwt
from fastapi.testclient import TestClient

from backend.config import get_settings
from backend.services.auth import AuthService
from backend.utils.tokens import decode_token


def _register(client: TestClient, username: str, password: str = "secret1") -> dict:
    resp = client.post(
        "/api/auth/register",
        json={"username": username, "password": password, "role": "student"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _login(client: TestClient, username: str, password: str) -> dict:
    resp = client.post(
        "/api/auth/login", json={"username": username, "password": password}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _legacy_token(user_id: int) -> str:
    """无 tv / typ 声明的旧式令牌（升级前签发），应按 tv=0 平滑兼容。"""
    now = dt.datetime.now(dt.timezone.utc)
    payload = {
        "sub": str(user_id),
        "role": "student",
        "iat": now,
        "exp": now + dt.timedelta(minutes=30),
    }
    return jwt.encode(payload, get_settings().auth_secret, algorithm="HS256")


def _probe(client: TestClient, token: str) -> int:
    """用受保护端点探活令牌。"""
    return client.get("/api/questions", headers=_header(token)).status_code


def test_change_password_revokes_old_tokens(client, db_session):
    tokens = _register(client, "revoke_pw_user")
    assert _probe(client, tokens["access_token"]) == 200

    result = AuthService(db_session).change_password(
        tokens["user_id"], "secret1", "secret2"
    )
    assert result.ok
    db_session.commit()  # 对 API 侧会话可见

    old = client.get(
        "/api/questions", headers=_header(tokens["access_token"])
    )
    assert old.status_code == 401
    assert old.json()["detail"] == "令牌已失效，请重新登录"

    new = _login(client, "revoke_pw_user", "secret2")
    assert _probe(client, new["access_token"]) == 200


def test_logout_revokes_old_tokens(client):
    tokens = _register(client, "logout_revoke_user")
    assert _probe(client, tokens["access_token"]) == 200

    resp = client.post("/api/auth/logout", headers=_header(tokens["access_token"]))
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}

    assert _probe(client, tokens["access_token"]) == 401

    fresh = _login(client, "logout_revoke_user", "secret1")
    assert _probe(client, fresh["access_token"]) == 200


def test_logout_rejects_stale_refresh_token(client):
    tokens = _register(client, "logout_refresh_user")
    client.post("/api/auth/logout", headers=_header(tokens["access_token"]))

    resp = client.post(
        "/api/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "令牌已失效，请重新登录"


def test_new_tokens_carry_current_token_version(client):
    tokens = _register(client, "tv_claim_user")
    claims = decode_token(tokens["access_token"])
    assert claims["tv"] == 0

    client.post("/api/auth/logout", headers=_header(tokens["access_token"]))
    fresh = _login(client, "tv_claim_user", "secret1")
    fresh_claims = decode_token(fresh["access_token"])
    assert fresh_claims["tv"] == 1
    assert _probe(client, fresh["access_token"]) == 200


def test_tokens_unaffected_without_revocation(client):
    first = _register(client, "stable_tokens_user")

    again = _login(client, "stable_tokens_user", "secret1")
    assert _probe(client, first["access_token"]) == 200
    assert _probe(client, again["access_token"]) == 200

    # refresh 轮换同样不受影响
    rotated = client.post(
        "/api/auth/refresh", json={"refresh_token": first["refresh_token"]}
    )
    assert rotated.status_code == 200, rotated.text
    assert _probe(client, rotated.json()["access_token"]) == 200

    # 旧令牌无 tv 声明按 0 兼容（用户 token_version 仍为 0）
    assert _probe(client, _legacy_token(first["user_id"])) == 200
