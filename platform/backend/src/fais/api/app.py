from __future__ import annotations

from contextlib import asynccontextmanager
from time import monotonic

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import PlainTextResponse

from fais.api.admin import router as admin_router
from fais.api.graphql import graphql_router
from fais.api.identity import router as identity_router
from fais.api.realtime import router as realtime_router
from fais.api.rest import router as rest_router
from fais.config import Settings
from fais.db import Database
from fais.db.migrate import migrate
from fais.db.repositories import SportsRepository
from fais.observability import RequestMetrics, system_metrics
from fais.workers.celery_app import celery_app


def create_app(settings: Settings | None = None) -> FastAPI:
    current = settings or Settings.from_env()
    current.validate_for_startup()
    database = Database(current.database_path)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        migrate(database)
        yield

    app = FastAPI(
        title="FAIS Sports Intelligence API",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )
    app.state.settings = current
    app.state.database = database
    app.state.repository = SportsRepository(database)
    app.state.celery = celery_app
    app.state.metrics = RequestMetrics()
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(current.allowed_hosts))
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(current.cors_origins),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Confirm-Action"],
    )
    app.include_router(rest_router)
    app.include_router(identity_router)
    app.include_router(admin_router)
    app.include_router(realtime_router)
    app.include_router(graphql_router, prefix="/graphql")

    @app.middleware("http")
    async def collect_metrics(request, call_next):
        started = monotonic()
        try:
            response = await call_next(request)
        except Exception:
            app.state.metrics.observe(500, monotonic() - started)
            raise
        app.state.metrics.observe(response.status_code, monotonic() - started)
        return response

    @app.get("/metrics", include_in_schema=False, response_class=PlainTextResponse)
    def metrics() -> str:
        return app.state.metrics.prometheus() + system_metrics(database, current.redis_url)

    return app
