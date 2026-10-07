"""Locust 压测脚本：对 API 做读路径负载模拟（只读基准，不做写路径压测）。

运行（需先启动 API + 已有 demo 账号）：
    locust -f locustfile.py --host http://localhost:8000 --headless -u 20 -r 5 -t 30s

负载权重（读路径）：列表 6 : 看板 3 : 到期 2 : 掌握度 1 : 语义搜索 1 :
完整备份 1 : 健康检查 1。写路径不入压测（20 VU 并发写会互相覆盖数据集，
污染基准与开发库），登录端点也不压（bcrypt 刻意慢是记录在案的安全开销）。
"""
from __future__ import annotations

import random

from locust import HttpUser, between, task

# SystemRandom 消除可预测随机性告警（压测关键词抽样，本非安全场景，顺手加固）
_rng = random.SystemRandom()
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
    def mastery_profile(self):
        self.client.get("/api/review/mastery", headers=self.headers, name="/api/review/mastery [read]")

    @task(1)
    def search_semantic(self):
        keyword = _rng.choice(["判别式", "几何", "函数", "方程", "概率"])
        self.client.get(
            "/api/questions",
            headers=self.headers,
            params={"keyword": keyword, "limit": 10},
            name="/api/questions?keyword [semantic]",
        )

    @task(1)
    def export_full(self):
        # 完整备份 zip：服务端实时生成（manifest+图片打包），属重低频读操作
        self.client.get(
            "/api/questions/export/full",
            headers=self.headers,
            name="/api/questions/export/full [zip]",
        )

    @task(1)
    def health(self):
        self.client.get("/health", name="/health [meta]")
