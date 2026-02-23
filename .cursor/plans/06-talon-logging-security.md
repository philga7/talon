
# Talon — Logging, Observability & Security

## Logging Stack

`structlog` (JSON lines) + optional OpenTelemetry tracing.
Every log entry: correlation ID, timestamp, level, component, structured fields.
No unstructured strings. No secrets in logs.

```python
import structlog, logging

def configure_logging(log_level="INFO", log_file="data/logs/talon.jsonl"):
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.filter_by_level,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            SecretMasker(),
            ErrorClassifier(),
            AlertEscalator(),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.WriteLoggerFactory(
            file=open(log_file, "a", buffering=1)
        ),
        cache_logger_on_first_use=True,
    )

class SecretMasker:
    PATTERNS = ["api_key", "token", "password", "secret", "authorization"]
    def __call__(self, logger, method, event_dict):
        for key in list(event_dict.keys()):
            if any(p in key.lower() for p in self.PATTERNS):
                event_dict[key] = "***REDACTED***"
        return event_dict
```

## Correlation ID Middleware

```python
import uuid, structlog
from starlette.middleware.base import BaseHTTPMiddleware

class CorrelationIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        cid = request.headers.get("X-Correlation-ID", str(uuid.uuid4()))
        structlog.contextvars.bind_contextvars(
            correlation_id=cid, path=request.url.path, method=request.method,
        )
        response = await call_next(request)
        response.headers["X-Correlation-ID"] = cid
        structlog.contextvars.clear_contextvars()
        return response
```

## Error Taxonomy

| Severity | Examples | Level | Action |
|---|---|---|---|
| `transient` | Provider timeout, HTTP 429 | WARNING | Auto-retry, no alert |
| `degraded` | All primary providers down | WARNING | UI warning badge via SSE |
| `critical` | All providers down, DB lost, OOM | ERROR | Log + push alert |
| `security` | Invalid auth, unexpected path access | ERROR | Log + immediate alert |

## Sample Log Entry

```json
{
  "timestamp": "2026-02-22T06:00:00.000Z",
  "level": "warning",
  "event": "provider_failed",
  "correlation_id": "7f3a1b2c-4d5e-6f7a-8b9c-0d1e2f3a4b5c",
  "provider": "primary",
  "error": "Connection timeout after 15s",
  "breaker_state": "open",
  "failures": 3,
  "error_class": "transient",
  "path": "/api/chat",
  "method": "POST"
}
```

## Security

### Pydantic BaseSettings (config.py)

```python
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings

class TalonSettings(BaseSettings):
    log_level: str = "INFO"
    debug: bool = False
    allowed_origins: list[str] = ["http://localhost:5173"]
    rate_limit_default: int = 100
    rate_limit_llm: int = 20

    # Secrets: each field maps to a file in config/secrets/
    db_password:      SecretStr        = Field(default=...)
    llm_api_keys:     SecretStr        = Field(default=...)
    discord_token:    SecretStr | None = None
    slack_bot_token:  SecretStr | None = None
    slack_app_token:  SecretStr | None = None
    session_secret:   SecretStr        = Field(default=...)

    model_config = {
        "env_file": ".env",
        "secrets_dir": "config/secrets",
    }
```

### Rate Limiting

```python
from collections import defaultdict
import time

class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, default_limit=100, llm_limit=20):
        super().__init__(app)
        self.counters = defaultdict(list)
        self.limits   = {"/api/chat": llm_limit, "/api/sse": llm_limit}
        self.default  = default_limit

    async def dispatch(self, request, call_next):
        ip, path, window = request.client.host, request.url.path, 60
        limit = self.limits.get(path, self.default)
        now   = time.monotonic()
        key   = f"{ip}:{path}"
        self.counters[key] = [ts for ts in self.counters[key] if now - ts < window]
        if len(self.counters[key]) >= limit:
            return JSONResponse(status_code=429,
                content={"error": "rate_limit_exceeded", "retry_after": window})
        self.counters[key].append(now)
        return await call_next(request)
```

### Security Checklist

- `config/secrets/` → chmod 700; files inside → chmod 600
- `config/talon.toml` → chmod 600
- `.env` → never contains secrets
- Git: `config/secrets/` and `config/talon.toml` in `.gitignore`
- API keys masked in all logs by `SecretMasker`
- CORS: explicit origin allowlist, no wildcard in production
- SQL: SQLAlchemy ORM or parameterized queries only
- Skill timeouts: every `execute()` wrapped in `asyncio.wait_for(timeout=30)`
- Input validation: all endpoints use Pydantic models
