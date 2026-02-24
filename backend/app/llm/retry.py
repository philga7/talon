"""Exponential backoff retry helpers."""

from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable
from typing import TypeVar

T = TypeVar("T")


async def retry_async(  # noqa: UP047
    operation: Callable[[], Awaitable[T]],
    *,
    max_attempts: int = 3,
    base_delay: float = 0.5,
    max_delay: float = 5.0,
) -> T:
    """Retry an async operation with exponential backoff and jitter.

    All exceptions are treated as retryable; callers should wrap only the
    section that is safe to retry (e.g. network I/O, not request building).
    """
    attempt = 0
    last_exc: BaseException | None = None

    while attempt < max_attempts:
        attempt += 1
        try:
            return await operation()
        except BaseException as exc:  # noqa: BLE001 - deliberate catch for retry
            last_exc = exc
            if attempt >= max_attempts:
                break

            # Exponential backoff with jitter
            delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
            jitter = random.uniform(0, delay * 0.1)
            await asyncio.sleep(delay + jitter)

    assert last_exc is not None  # for type-checkers
    raise last_exc
