#!/usr/bin/env python
"""REST API 使用示例：登录 → 录题 → 复习 → 统计 的完整链路。

前置：uvicorn api.main:app --port 8000
运行：python examples/api_walkthrough.py
"""
import json
import os
import sys
import urllib.request
from urllib.parse import urlparse


def _check_base(url: str) -> str:
    """BASE 安全边界：仅 http(s)、非回环主机需显式 MM_ALLOW_REMOTE_HOST=1。"""
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in ("http", "https") or not host:
        raise SystemExit(f"BASE 必须是合法 http(s) 地址: {url}")
    loopback = host in ("localhost", "127.0.0.1", "::1")
    if not loopback and os.getenv("MM_ALLOW_REMOTE_HOST") != "1":
        raise SystemExit(f"拒绝请求非回环地址 {host}：确认目标后设 MM_ALLOW_REMOTE_HOST=1")
    return url


BASE = _check_base("http://localhost:8000")


def request(method: str, path: str, token: str | None = None, data=None):
    headers = {}
    body = None
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if data is not None:
        body = json.dumps(data).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(BASE + path, data=body, headers=headers, method=method)
    with urllib.request.urlopen(req) as resp:
        raw = resp.read()
        return json.loads(raw) if raw else None


def main() -> None:
    # 1. 登录拿 JWT
    login = request(
        "POST",
        "/api/auth/login",
        data={"username": "demo", "password": "demo123"},
    )
    token = login["access_token"]
    print(f"[1] 登录成功 user={login['username']}")

    # 2. 手动录入一道错题（图片 AI 解析见 scripts/smoke_api.py）
    question = request(
        "POST",
        "/api/questions/text",
        token=token,
        data={
            "content_markdown": "示例题：已知 $x^2=9$，求 x。",
            "answer": "x=±3",
            "tags": ["示例", "方程"],
        },
    )
    print(f"[2] 录题成功 id={question['id']}")

    # 3. 复习评分（SM-2 自动排期）
    graded = request(
        "POST",
        f"/api/review/{question['id']}/grade",
        token=token,
        data={"grade": "good"},
    )
    print(f"[3] 评分成功 下次间隔={graded['interval_days']:.0f} 天")

    # 4. 追问讲题
    reply = request(
        "POST",
        f"/api/review/{question['id']}/followup",
        token=token,
        data={"question": "为什么有两个解？", "history": []},
    )
    print(f"[4] 追问回复：{reply['reply'][:50]}…")

    # 5. 学情统计与标签图谱
    dash = request("GET", "/api/stats/dashboard", token=token)
    graph = request("GET", "/api/stats/tag-graph", token=token)
    print(f"[5] 看板 total={dash['total']} due={dash['due']}；共现边 {len(graph)} 条")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001
        print(f"失败：{exc}\n请确认 API 已启动：uvicorn api.main:app --port 8000")
        sys.exit(1)
