"""任务队列抽象（Batch 08）测试：线程后端、RQ 后端（fakeredis）、取消语义。"""
from __future__ import annotations

import time
import uuid

import pytest

from backend.database import SessionLocal
from backend.jobs.queue import RQJobQueue, ThreadedJobQueue, get_job_queue
from backend.models.orm import Job
from backend.services.job_service import JobService


def _fake_png_bytes() -> bytes:
    # mock AI provider 不做真实视觉解析，任意字节即可
    return b"\x89PNG\r\n\x1a\n" + b"z" * 32


class TestQueueFactory:
    def test_default_is_threaded(self):
        assert isinstance(get_job_queue(None), ThreadedJobQueue)
        assert isinstance(get_job_queue(""), ThreadedJobQueue)

    def test_redis_url_selects_rq(self):
        queue = get_job_queue("redis://localhost:6379/0")
        assert isinstance(queue, RQJobQueue)


class TestThreadedBackend:
    def test_submit_analyze_end_to_end(self, student_user):
        service = JobService()
        job_id = service.submit_analyze(
            student_user.id,
            _fake_png_bytes(),
            filename="t.png",
            mime_type="image/png",
            tags=["队列"],
        )
        deadline = time.time() + 15
        status = None
        while time.time() < deadline:
            info = service.get(job_id, student_user.id)
            status = info["status"]
            if status in {"success", "failed", "cancelled"}:
                break
            time.sleep(0.2)
        assert status == "success", f"任务应执行成功，实际 {status}"
        assert service.get(job_id, student_user.id)["result"]["duplicated"] in {True, False}

    def test_cancel_pending_job(self, student_user):
        service = JobService()
        job_id = service.submit_analyze(
            student_user.id, _fake_png_bytes(), filename="t2.png", mime_type="image/png"
        )
        # 立即取消（任务尚未被线程处理完也可能已 running——两种结果都合法）
        outcome = service.cancel(job_id, student_user.id)
        info = service.get(job_id, student_user.id)
        assert info["status"] in {"cancelled", "running", "success", "failed"}
        if info["status"] == "cancelled":
            assert outcome is True
        # 重复取消：非 pending 状态应失败
        assert service.cancel(job_id, student_user.id) is False

    def test_get_isolated_by_user(self, student_user):
        service = JobService()
        job_id = service.submit_analyze(
            student_user.id, _fake_png_bytes(), filename="t3.png", mime_type="image/png"
        )
        assert service.get(job_id, user_id=99999999) is None


class TestRQBackend:
    @staticmethod
    def _make_pending_job(student_user, job_id: str) -> None:
        """直接建 pending 任务行：绕过 submit_analyze 的后端派发，专测 RQ 链路。"""
        from backend.config import get_settings

        image_path = get_settings().data_dir / "jobs" / f"{job_id}.jpg"
        image_path.parent.mkdir(parents=True, exist_ok=True)
        image_path.write_bytes(_fake_png_bytes())
        with SessionLocal() as session:
            session.add(
                Job(
                    id=job_id,
                    user_id=student_user.id,
                    type="analyze_image",
                    status="pending",
                    payload={
                        "filename": "rq.png",
                        "mime_type": "image/png",
                        "image_path": str(image_path),
                        "tags": ["RQ"],
                    },
                )
            )
            session.commit()

    def test_enqueue_and_worker_burst(self, student_user):
        """fakeredis 模拟 Redis：入队 → Worker burst 消费 → jobs 表落终态。"""
        from fakeredis import FakeRedis
        from rq import Queue, SimpleWorker

        job_id = f"rqq{uuid.uuid4().hex[:10]}"
        self._make_pending_job(student_user, job_id)

        connection = FakeRedis()
        queue = Queue("mathmaster", connection=connection)
        queue.enqueue("backend.jobs.tasks.run_analyze_job", job_id, student_user.id)

        worker = SimpleWorker([queue], connection=connection)
        worker.work(burst=True)

        info = JobService().get(job_id, student_user.id)
        assert info["status"] == "success", info

    def test_worker_skips_cancelled_job(self, student_user):
        from fakeredis import FakeRedis
        from rq import Queue, SimpleWorker

        with SessionLocal() as session:
            job = Job(
                id="rqcancel01",
                user_id=student_user.id,
                type="analyze_image",
                status="cancelled",
                payload={"filename": "x.png", "mime_type": "image/png"},
            )
            session.add(job)
            session.commit()

        connection = FakeRedis()
        queue = Queue("mathmaster", connection=connection)
        queue.enqueue("backend.jobs.tasks.run_analyze_job", "rqcancel01", student_user.id)
        SimpleWorker([queue], connection=connection).work(burst=True)

        with SessionLocal() as session:
            status = session.get(Job, "rqcancel01").status
        assert status == "cancelled", "已取消任务不应被 Worker 执行"


class TestCancelAPI:
    @pytest.fixture
    def job_headers(self, client):
        username = f"jobq_{uuid.uuid4().hex[:10]}"
        client.post(
            "/api/auth/register",
            json={"username": username, "password": "secret1", "role": "student"},
        )
        login = client.post(
            "/api/auth/login", json={"username": username, "password": "secret1"}
        )
        return {"Authorization": f"Bearer {login.json()['access_token']}"}, username

    def test_cancel_endpoint(self, client, job_headers):
        headers, username = job_headers
        from backend.models.orm import User

        with SessionLocal() as session:
            user = session.query(User).filter_by(username=username).one()
            session.add(
                Job(
                    id="apicancel01",
                    user_id=user.id,
                    type="analyze_image",
                    status="pending",
                    payload={"filename": "x.png", "mime_type": "image/png"},
                )
            )
            session.commit()

        assert (
            client.post("/api/jobs/apicancel01/cancel", headers=headers).status_code == 204
        )
        # 再次取消 → 409（已不是 pending）
        assert (
            client.post("/api/jobs/apicancel01/cancel", headers=headers).status_code == 409
        )
        info = client.get("/api/jobs/apicancel01", headers=headers).json()
        assert info["status"] == "cancelled"
