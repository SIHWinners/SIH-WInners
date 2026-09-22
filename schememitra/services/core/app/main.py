"""FastAPI application factory."""

import importlib
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from app.config import get_settings
from app.core.ids import uuid7
from app.errors import install_error_handlers
from app.logging import configure_logging, get_logger

log = get_logger("app")

# Order matters only for the OpenAPI document layout.
ROUTER_MODULES = ["system", "auth", "eligibility", "finance", "routing", "documents", "applications", "voice", "ranking", "partner"]


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    from app.bootstrap import startup

    await startup()
    yield
    from app.db.session import dispose_engine

    await dispose_engine()


def create_app() -> FastAPI:
    s = get_settings()
    configure_logging("WARNING" if s.env == "test" else "INFO")
    app = FastAPI(
        title="SchemeMitra Core API",
        version="1.0.0",
        description="Deterministic eligibility, repayment maths, partner routing, documents, voice and "
        "application tracking for marginalized entrepreneurs. Money is integer paise; rates are bps.",
        lifespan=lifespan,
        openapi_url="/openapi.json",
        docs_url="/docs",
    )
    app.add_middleware(GZipMiddleware, minimum_size=800)
    app.add_middleware(
        CORSMiddleware, allow_origins=s.cors_origins, allow_credentials=True,
        allow_methods=["*"], allow_headers=["*"],
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next):  # type: ignore[no-untyped-def]
        started = time.perf_counter()
        request_id = request.headers.get("x-request-id") or str(uuid7())
        response: Response = await call_next(request)
        elapsed_ms = (time.perf_counter() - started) * 1000
        response.headers["x-request-id"] = request_id
        response.headers["server-timing"] = f"app;dur={elapsed_ms:.1f}"
        response.headers["x-content-type-options"] = "nosniff"
        response.headers["referrer-policy"] = "no-referrer"
        if elapsed_ms > 500:
            log.info("slow request %s %s %.0fms", request.method, request.url.path, elapsed_ms)
        return response

    install_error_handlers(app)

    for module in ROUTER_MODULES:
        app.include_router(importlib.import_module(f"app.modules.{module}.router").router)
    return app
