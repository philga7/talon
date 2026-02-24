"""Circuit breaker implementation for LLM providers."""

from __future__ import annotations

from dataclasses import dataclass, field
from time import monotonic
from typing import Literal

BreakerState = Literal["closed", "open", "half_open"]


@dataclass
class CircuitBreaker:
    """Simple circuit breaker with OPEN → HALF_OPEN → CLOSED transitions.

    - When failures reach `failure_threshold`, the breaker opens.
    - While open, calls are blocked until `recovery_timeout` seconds elapse.
    - After timeout, the breaker enters HALF_OPEN and allows a single probe call.
    - On probe success, the breaker closes and resets counters.
    - On probe failure, the breaker opens again and the timeout resets.
    """

    name: str
    failure_threshold: int = 3
    recovery_timeout: float = 60.0
    _state: BreakerState = field(default="closed", init=False)
    _failure_count: int = field(default=0, init=False)
    _opened_at: float | None = field(default=None, init=False)

    def current_state(self) -> BreakerState:
        """Return the current state, updating OPEN → HALF_OPEN when timeout elapses."""
        if self._state == "open" and self._opened_at is not None:
            elapsed = monotonic() - self._opened_at
            if elapsed >= self.recovery_timeout:
                self._state = "half_open"
        return self._state

    def can_attempt(self) -> bool:
        """Return True if a call should be attempted."""
        state = self.current_state()
        return state in ("closed", "half_open")

    def record_success(self) -> None:
        """Record a successful call and close the breaker."""
        self._failure_count = 0
        self._state = "closed"
        self._opened_at = None

    def record_failure(self) -> None:
        """Record a failed call and transition state if needed."""
        self._failure_count += 1
        state = self.current_state()

        if state in ("closed", "half_open") and self._failure_count >= self.failure_threshold:
            self._state = "open"
            self._opened_at = monotonic()

    @property
    def failure_count(self) -> int:
        return self._failure_count

    def opened_seconds_ago(self) -> float | None:
        """Return seconds since breaker opened, or None if not open."""
        if self._state != "open" or self._opened_at is None:
            return None
        return monotonic() - self._opened_at
