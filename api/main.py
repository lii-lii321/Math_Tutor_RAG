"""FastAPI 网关：把 backend 服务暴露为 REST API，供多端复用。

启动：uvicorn api.main:app --port 8000
文档：http://localhost:8000/docs
"""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

from api.routers import (
    agent,
    auth,
    classes,
    comments,
    conversations,
    jobs,
    questions,
    review,
    stats,
    tags,
)
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
        # 生产通过 CORS_ORIGINS 环境变量收紧，如 https://app.example.com,https://m.example.com
        allow_origins=[
            origin.strip()
            for origin in settings.cors_origins.split(",")
            if origin.strip()
        ]
        or ["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(auth.router, prefix=settings.api_prefix)
    app.include_router(questions.router, prefix=settings.api_prefix)
    app.include_router(review.router, prefix=settings.api_prefix)
    app.include_router(stats.router, prefix=settings.api_prefix)
    app.include_router(tags.router, prefix=settings.api_prefix)
    app.include_router(comments.router, prefix=settings.api_prefix)
    app.include_router(classes.router, prefix=settings.api_prefix)
    app.include_router(agent.router, prefix=settings.api_prefix)
    app.include_router(conversations.router, prefix=settings.api_prefix)
    app.include_router(jobs.router, prefix=settings.api_prefix)

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("未处理异常 %s %s: %s", request.method, request.url.path, exc)
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误"})

    @app.middleware("http")
    async def _metrics_middleware(request: Request, call_next):
        """Prometheus HTTP 指标：路由模板做 path 标签（防 ID 级基数爆炸）。

        route 在 call_next 内部（路由器）才解析进 scope，必须在响应后读取。
        """
        import time

        from backend.observability import observe_http

        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            template = request.scope.get("route")
            observe_http(
                request.method,
                getattr(template, "path", "unmatched"),
                500,
                time.perf_counter() - started,
            )
            raise
        route = request.scope.get("route")
        observe_http(
            request.method,
            route.path if route is not None else "unmatched",
            response.status_code,
            time.perf_counter() - started,
        )
        return response

    @app.get("/metrics", tags=["meta"], include_in_schema=False)
    def metrics() -> Response:
        """Prometheus 抓取端点；公开可读，生产应在网关限制来源。"""
        from backend.observability import render_metrics

        body, content_type = render_metrics()
        return Response(content=body, media_type=content_type)

    @app.on_event("startup")
    def _reap_stuck_jobs() -> None:
        """启动期回收进程崩溃遗留的 running 任务（超时 30 分钟）。"""
        try:
            from backend.services.job_service import JobService

            JobService.reap_stuck_jobs(timeout_minutes=30)
        except Exception:  # noqa: BLE001 - 回收失败不阻断启动
            logger.warning("启动期任务回收失败", exc_info=True)

    @app.get("/health", tags=["meta"])
    def health() -> dict:
        from backend.database import check_connection

        db_ok = check_connection()
        return {
            "status": "ok" if db_ok else "degraded",
            "version": settings.app_version,
            "db": "ok" if db_ok else "unreachable",
        }

    return app


app = create_app()
