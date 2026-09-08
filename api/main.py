"""FastAPI 网关：把 backend 服务暴露为 REST API，供多端复用。

启动：uvicorn api.main:app --port 8000
文档：http://localhost:8000/docs
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routers import auth, questions, review, stats
from backend.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=f"{settings.app_name} API",
        version=settings.app_version,
        description=(
            "智能错题本 REST API：认证 / 错题管理 / AI 录题 / 复习调度 / 学情统计。"
            "所有受保护端点使用 Bearer JWT。"
        ),
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # 部署时通过反向代理收紧
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(auth.router, prefix=settings.api_prefix)
    app.include_router(questions.router, prefix=settings.api_prefix)
    app.include_router(review.router, prefix=settings.api_prefix)
    app.include_router(stats.router, prefix=settings.api_prefix)

    @app.get("/health", tags=["meta"])
    def health() -> dict:
        return {"status": "ok", "version": settings.app_version}

    return app


app = create_app()
