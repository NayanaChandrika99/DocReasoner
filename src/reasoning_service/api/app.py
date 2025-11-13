"""FastAPI application factory."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import make_asgi_app

from reasoning_service.config import settings
from reasoning_service.api.routes import health, reason
from reasoning_service.api.middleware import RequestLoggingMiddleware, MetricsMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Lifespan context manager for startup/shutdown logic."""
    # Startup
    # TODO: Initialize database connections, caches, etc.
    yield
    # Shutdown
    # TODO: Close connections, cleanup resources


def create_app() -> FastAPI:
    """Create and configure FastAPI application.
    
    Returns:
        Configured FastAPI application
    """
    app = FastAPI(
        title=settings.app_name,
        description="Reasoning Layer for Prior Authorization",
        version="0.1.0",
        debug=settings.debug,
        lifespan=lifespan
    )
    
    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # TODO: Configure for production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Custom middleware
    app.add_middleware(RequestLoggingMiddleware)
    if settings.metrics_enabled:
        app.add_middleware(MetricsMiddleware)
    
    # Routes
    app.include_router(health.router, prefix="/health", tags=["health"])
    app.include_router(reason.router, prefix="/reason", tags=["reasoning"])
    
    # Prometheus metrics endpoint
    if settings.metrics_enabled:
        metrics_app = make_asgi_app()
        app.mount("/metrics", metrics_app)
    
    return app
