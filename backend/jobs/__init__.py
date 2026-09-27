"""后台任务模块（Batch 08）：任务函数 / 队列后端 / Worker 入口。

执行链路二选一（由 REDIS_URL 决定）：
- 默认：FastAPI/Streamlit 进程内后台线程（零依赖，单实例部署）
- 配置 REDIS_URL：RQ 队列 + 独立 Worker 进程（多实例/生产部署）

  uvicorn api.main:app --port 8000
  python -m backend.jobs.worker        # 消费 mathmaster 队列

jobs 表仍是唯一状态源：pending → running → success/failed/cancelled。
"""
from backend.jobs.queue import JobQueue, RQJobQueue, ThreadedJobQueue, get_job_queue

__all__ = ["JobQueue", "ThreadedJobQueue", "RQJobQueue", "get_job_queue"]
