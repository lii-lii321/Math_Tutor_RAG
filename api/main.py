"""FastAPI 网关：把 backend 服务暴露为 REST API，供多端复用。

启动：uvicorn api.main:app --port 8000
文档：http://localhost:8000/docs
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routers import agent, auth, comments, jobs, questions, review, stats, tags
from backend.config import Settings, get_settings
from backend.utils.logging import get_logger

logger = get_logger("api")


def _init_sentry(settings: Settings) -> None:
    """可选的错误上报：配置 SENTRY_DSN 后启用（依赖缺失时仅告警）。"""
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration

        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            traces_sample_rate=settings.sentry_traces_sample_rate,
            release=f"mathmaster@{settings.app_version}",
            integrations=[FastApiIntegration()],
        )
        logger.info("Sentry 已启用")
    except ImportError:
        logger.warning("SENTRY_DSN 已配置但 sentry-sdk 未安装：pip install sentry-sdk[fastapi]")


def create_app() -> FastAPI:
    settings = get_settings()
    if settings.sentry_dsn:
        _init_sentry(settings)

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
    app.include_router(tags.router, prefix=settings.api_prefix)
    app.include_router(comments.router, prefix=settings.api_prefix)
    app.include_router(agent.router, prefix=settings.api_prefix)
    app.include_router(jobs.router, prefix=settings.api_prefix)

    @app.get("/health", tags=["meta"])
    def health() -> dict:
        return {"status": "ok", "version": settings.app_version}

    return app


app = create_app()
