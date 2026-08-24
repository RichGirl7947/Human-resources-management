import asyncio
from contextlib import asynccontextmanager, suppress
import logging
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .api import router
from .audit import AuditMiddleware
from .auth import validate_production_settings
from .auth_api import router as auth_router
from .config import get_settings
from .database import SessionLocal, init_db
from .notifications import dispatch_due_notifications


settings = get_settings()
logging.basicConfig(level=settings.log_level)


def _dispatch_notifications() -> None:
    with SessionLocal() as db:
        dispatch_due_notifications(db)


async def _notification_worker() -> None:
    while True:
        await asyncio.sleep(settings.notification_poll_seconds)
        try:
            await asyncio.to_thread(_dispatch_notifications)
        except Exception:
            logging.exception("Interview notification worker failed")


@asynccontextmanager
async def lifespan(_: FastAPI):
    validate_production_settings()
    init_db()
    worker = None
    if settings.environment != "test" and not settings.celery_broker_url:
        worker = asyncio.create_task(_notification_worker())
    try:
        yield
    finally:
        if worker:
            worker.cancel()
            with suppress(asyncio.CancelledError):
                await worker


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="员工全生命周期人力资源 Agent MVP",
    lifespan=lifespan,
    docs_url="/docs" if settings.docs_enabled else None,
    redoc_url="/redoc" if settings.docs_enabled else None,
    openapi_url="/openapi.json" if settings.docs_enabled else None,
)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(settings.allowed_hosts))
app.add_middleware(AuditMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth_router)
app.include_router(router)


@app.middleware("http")
async def security_headers(request: Any, call_next: Any) -> Any:
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; base-uri 'self'; frame-ancestors 'none'; object-src 'none'; "
        "script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
        "connect-src 'self'"
    )
    if settings.environment == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response

frontend_dist = Path(os.getenv("HR_FRONTEND_DIR", Path.cwd() / "frontend" / "dist")).resolve()
assets_dir = frontend_dist / "assets"
if assets_dir.exists():
    app.mount("/assets", StaticFiles(directory=assets_dir), name="frontend-assets")


@app.get("/", include_in_schema=False)
def root() -> Any:
    index_file = frontend_dist / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return {"name": settings.app_name, "docs": "/docs", "health": "/health"}


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok", "environment": settings.environment}


@app.get("/health/ready", tags=["system"])
def readiness() -> dict[str, str]:
    with SessionLocal() as db:
        db.execute(text("SELECT 1"))
    return {"status": "ready", "database": "ok"}
