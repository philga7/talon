"""API key auth helpers."""

from fastapi import Header, HTTPException, status


def require_api_key(x_api_key: str | None = Header(default=None)) -> str:
    """Validate X-API-Key header. For Phase 1, accepts any non-empty value."""
    if not x_api_key or not x_api_key.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "missing_api_key", "message": "X-API-Key header required"},
        )
    return x_api_key.strip()
