import asyncio
import logging
import secrets
import time
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.activity.worker import worker as activity_worker
from app.api import (
    activity,
    adaptive,
    analyses,
    auth,
    chat,
    exams,
    learning,
    materials,
    providers,
    reviews,
    spaces,
)
from app.api.deps import RateLimiter
from app.core.security import CredentialVault, password_hash
from app.core.settings import Settings
from app.db.session import build_database
from app.exam_diagnostics.worker import worker as exam_worker
from app.jobs.materials import worker
from app.providers.base import ProviderError

logger = logging.getLogger("uvicorn.error.study_agent")


def create_app(settings=None, adapter_factory=None):
    settings = settings or Settings()
    from app.learner.parameters import load_parameter_bundle

    bundle = load_parameter_bundle(settings.learner_parameters_path)
    engine, sessions = build_database(settings.database_url)
    sessions.configure(info={"algorithm_parameters": bundle})

    @asynccontextmanager
    async def lifespan(app):
        task = asyncio.create_task(worker(app)) if settings.material_worker_enabled else None
        app.state.activity_worker_task = (
            asyncio.create_task(activity_worker(app)) if settings.m4_worker_enabled else None
        )
        exam_task = asyncio.create_task(exam_worker(app)) if settings.exam_worker_enabled else None
        try:
            yield
        finally:
            if exam_task:
                exam_task.cancel()
                with suppress(asyncio.CancelledError):
                    await exam_task
            if app.state.activity_worker_task:
                app.state.activity_worker_task.cancel()
                with suppress(asyncio.CancelledError):
                    await app.state.activity_worker_task
            if task:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
            engine.dispose()

    app = FastAPI(
        title="StudyAgent Framework",
        version="0.1.0",
        lifespan=lifespan,
        description="围绕学习目标，提供诊断、教学、练习、间隔复习、学习报告与 AI 分析，持续记录个人学习进度。",
    )
    app.state.settings = settings
    app.state.engine, app.state.session_factory = engine, sessions
    app.state.vault = CredentialVault(settings.credential_encryption_key)
    app.state.adapter_factory = adapter_factory
    app.state.sqlite_lock = asyncio.Lock()
    app.state.limiter = RateLimiter()
    app.state.dummy_password_hash = password_hash(secrets.token_urlsafe(20))

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request_id, start = secrets.token_hex(12), time.monotonic()
        request.state.request_id = request_id
        if (
            request.method not in {"GET", "HEAD", "OPTIONS"}
            and (Path(settings.material_storage_dir) / ".maintenance-lock").exists()
        ):
            return JSONResponse(
                {"error": {"code": "maintenance", "message": "学习数据维护中，请稍后重试"}}, status_code=503
            )
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            origin = request.headers.get("origin")
            allowed = {str(request.base_url).rstrip("/"), settings.frontend_origin.rstrip("/")}
            if origin and origin.rstrip("/") not in allowed:
                return JSONResponse(
                    {"error": {"code": "csrf_rejected", "message": "不允许跨站修改请求"}}, status_code=403
                )
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["X-Frame-Options"] = "DENY"
        if request.url.path.startswith("/api"):
            response.headers["Cache-Control"] = "no-store"
        route = request.scope.get("route")
        logger.info(
            "request_id=%s method=%s route=%s status=%s elapsed_ms=%d",
            request_id,
            request.method,
            getattr(route, "path", "unmatched"),
            response.status_code,
            int((time.monotonic() - start) * 1000),
        )
        return response

    @app.exception_handler(ProviderError)
    async def provider_error(request, exc):
        return JSONResponse(
            {"error": {"code": exc.code, "message": exc.message}, "request_id": request.state.request_id},
            status_code=exc.status,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        return JSONResponse(
            {
                "error": {
                    "code": "validation_error",
                    "message": "输入字段不合法",
                    "fields": [{"loc": e["loc"], "type": e["type"]} for e in exc.errors()],
                }
            },
            status_code=422,
        )

    @app.exception_handler(IntegrityError)
    async def integrity_error(request, exc):
        return JSONResponse(
            {"error": {"code": "conflict", "message": "数据已存在或请求冲突，请刷新后重试"}}, status_code=409
        )

    @app.get("/health", tags=["system"])
    async def health():
        with sessions() as db:
            db.execute(text("SELECT 1"))
        return {"status": "ok", "phase": "M4"}

    @app.get("/api/v1/config", tags=["system"])
    async def public_config():
        return {
            "demo_enabled": settings.enable_fake_provider,
            "phase": "M4",
            "material_max_bytes": settings.material_max_bytes,
        }

    for router in (
        auth.router,
        exams.router,
        providers.router,
        spaces.router,
        learning.router,
        materials.router,
        reviews.router,
        adaptive.router,
        chat.router,
        activity.router,
        analyses.router,
    ):
        app.include_router(router, prefix="/api/v1")
    dist = Path(settings.frontend_dist)
    if (dist / "assets").exists():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")
    if (dist / "index.html").exists():

        @app.get("/", include_in_schema=False)
        @app.get("/login", include_in_schema=False)
        @app.get("/register", include_in_schema=False)
        async def web():
            return FileResponse(dist / "index.html")

    return app
