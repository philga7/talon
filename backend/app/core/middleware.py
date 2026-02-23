"""Correlation ID and rate limit middleware."""

import time
import uuid
from collections import defaultdict

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

log = structlog.get_logger()


class CorrelationIDMiddleware(BaseHTTPMiddleware):
    """Adds X-Correlation-ID to requests and binds it to structlog context."""

    async def dispatch(self, request: Request, call_next: object) -> Response:
        cid = request.headers.get("X-Correlation-ID") or str(uuid.uuid4())
        structlog.contextvars.bind_contextvars(
            correlation_id=cid,
            path=request.url.path,
            method=request.method,
        )
        response = await call_next(request)
        response.headers["X-Correlation-ID"] = cid
        structlog.contextvars.clear_contextvars()
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Per-IP rate limiting with configurable limits per path."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        default_limit: int = 100,
        llm_limit: int = 20,
        window_seconds: int = 60,
    ) -> None:
        super().__init__(app)
        self._counters: dict[str, list[float]] = defaultdict(list)
        self._limits: dict[str, int] = {
            "/api/chat": llm_limit,
            "/api/sse": llm_limit,
        }
        self._default = default_limit
        self._window = window_seconds

    def _limit_for_path(self, path: str) -> int:
        for prefix, limit in self._limits.items():
            if path.startswith(prefix):
                return limit
        return self._default

    async def dispatch(self, request: Request, call_next: object) -> Response:
        client = request.client
        ip = client.host if client else "unknown"
        path = request.url.path
        limit = self._limit_for_path(path)
        key = f"{ip}:{path}"

        now = time.monotonic()
        self._counters[key] = [ts for ts in self._counters[key] if now - ts < self._window]

        if len(self._counters[key]) >= limit:
            log.warning("rate_limit_exceeded", key=key, limit=limit)
            return JSONResponse(
                status_code=429,
                content={
                    "error": "rate_limit_exceeded",
                    "retry_after": self._window,
                },
            )

        self._counters[key].append(now)
        return await call_next(request)
