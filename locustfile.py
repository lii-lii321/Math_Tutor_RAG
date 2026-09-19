"""Locust 压测脚本：对 API 做读多写少的真实负载模拟。

运行（需先启动 API + 已有 demo 账号）：
    locust -f locustfile.py --host http://localhost:8000 --headless -u 20 -r 5 -t 30s

写操作刻意限频（每虚拟用户 ~1次/10s），读操作为主，避免测试数据爆炸。
"""
from __future__ import annotations

import random

from locust import HttpUser, between, task

_DEMO = {"username": "demo", "password": "demo123"}


class MathMasterUser(HttpUser):
    wait_time = between(1, 3)

    def on_start(self):
        resp = self.client.post("/api/auth/login", json=_DEMO)
        if resp.status_code == 200:
            self.token = resp.json()["access_token"]
            self.headers = {"Authorization": f"Bearer {self.token}"}
        else:
            self.headers = {}

    @task(6)
    def list_questions(self):
        self.client.get(
            "/api/questions",
            headers=self.headers,
            params={"limit": 20},
            name="/api/questions [read]",
        )

    @task(3)
    def dashboard(self):
        self.client.get("/api/stats/dashboard", headers=self.headers, name="/api/stats/dashboard [read]")

    @task(2)
    def due_questions(self):
        self.client.get("/api/review/due", headers=self.headers, name="/api/review/due [read]")

    @task(1)
    def search_semantic(self):
        keyword = random.choice(["判别式", "几何", "函数", "方程", "概率"])
        self.client.get(
            "/api/questions",
            headers=self.headers,
            params={"keyword": keyword, "limit": 10},
            name="/api/questions?keyword [semantic]",
        )

    @task(1)
    def health(self):
        self.client.get("/health", name="/health [meta]")
