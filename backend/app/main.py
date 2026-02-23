"""FastAPI app factory with lifespan context manager."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.chat import router as chat_router
from app.api.health import router as health_router
from app.api.memory import router as memory_router
from app.api.sse import router as sse_router
from app.core.config import TalonSettings, get_settings, init_settings
from app.core.logging import configure_logging
from app.core.middleware import CorrelationIDMiddleware, RateLimitMiddleware
from app.dependencies import init_db, init_gateway, init_memory


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown hooks."""
    settings: TalonSettings = get_settings()
    configure_logging(
        log_level=settings.log_level,
        log_file=settings.log_file_path,
    )
    init_db(settings)
    init_gateway(settings)
    init_memory(settings)
    yield
    # Shutdown: close DB connections, etc.
    # SQLAlchemy engine cleanup happens when app is destroyed


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = init_settings()

    app = FastAPI(
        title="Talon",
        description="Self-hosted personal AI gateway",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(CorrelationIDMiddleware)
    app.add_middleware(
        RateLimitMiddleware,
        default_limit=settings.rate_limit_default,
        llm_limit=settings.rate_limit_llm,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health_router)
    app.include_router(memory_router)
    app.include_router(chat_router)
    app.include_router(sse_router)

    return app


app = create_app()
