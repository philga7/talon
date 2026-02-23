
# Talon — LLM Gateway

The gateway is the only place in the codebase that talks to LLM providers.
Everything else is deterministic. This is intentional.

## Provider Chain

```
providers.yaml defines priority order:

  Primary   → high context window
  Fallback  → standard context window
  Others    → additional configured providers

Each provider has an independent circuit breaker.
Failure on one provider triggers promotion to the next.
```

## Circuit Breaker States

```
              3 failures in 60s
  CLOSED ──────────────────────► OPEN
    ▲                              │
    │  probe succeeds              │ 60s timeout
    │                              ▼
    └──────────────────────── HALF_OPEN
         probe fails → OPEN again
```

## circuit_breaker.py

```python
import time
from enum import Enum
from dataclasses import dataclass, field

class BreakerState(str, Enum):
    CLOSED    = "closed"
    OPEN      = "open"
    HALF_OPEN = "half_open"

@dataclass
class CircuitBreaker:
    name: str
    failure_threshold: int   = 3
    recovery_timeout:  float = 60.0

    failure_count:     int   = field(default=0, init=False)
    last_failure_time: float = field(default=0.0, init=False)
    _state: BreakerState     = field(default=BreakerState.CLOSED, init=False)

    @property
    def state(self) -> BreakerState:
        if self._state == BreakerState.OPEN:
            if time.monotonic() - self.last_failure_time >= self.recovery_timeout:
                return BreakerState.HALF_OPEN
        return self._state

    def record_success(self):
        self.failure_count = 0
        self._state = BreakerState.CLOSED

    def record_failure(self):
        self.failure_count += 1
        self.last_failure_time = time.monotonic()
        if self.failure_count >= self.failure_threshold:
            self._state = BreakerState.OPEN

    def allow_request(self) -> bool:
        return self.state in (BreakerState.CLOSED, BreakerState.HALF_OPEN)
```

## providers.yaml

```yaml
providers:
  - name: primary
    model: your-primary-model
    priority: 1
    timeout: 60
    max_retries: 3

  - name: fallback
    model: your-fallback-model
    priority: 2
    timeout: 30
    max_retries: 2

  - name: secondary
    model: your-secondary-model
    priority: 3
    timeout: 30
    max_retries: 1

  - name: tertiary
    model: your-tertiary-model
    priority: 4
    timeout: 30
    max_retries: 1
```

## gateway.py

```python
import asyncio
from litellm import acompletion
from app.llm.circuit_breaker import CircuitBreaker, BreakerState
from app.llm.models import LLMResponse, ProviderConfig
from app.core.errors import AllProvidersDown
import structlog

log = structlog.get_logger()

class LLMGateway:
    def __init__(self, providers: list[ProviderConfig]):
        self.providers = sorted(providers, key=lambda p: p.priority)
        self.breakers  = {p.name: CircuitBreaker(name=p.name) for p in providers}

    async def complete(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        tool_choice: str = "auto",
    ) -> LLMResponse:
        last_error = None
        for provider in self.providers:
            cb = self.breakers[provider.name]
            if not cb.allow_request():
                log.debug("provider_skipped", provider=provider.name,
                          breaker=cb.state)
                continue
            try:
                response = await asyncio.wait_for(
                    acompletion(
                        model=provider.model,
                        messages=messages,
                        tools=tools,
                        tool_choice=tool_choice if tools else None,
                        api_key=provider.api_key,
                    ),
                    timeout=provider.timeout,
                )
                cb.record_success()
                return LLMResponse.from_litellm(response, provider.name)
            except Exception as e:
                cb.record_failure()
                last_error = e
                log.warning("provider_failed", provider=provider.name,
                            error=str(e), failures=cb.failure_count,
                            breaker=cb.state)

        status = {p.name: self.breakers[p.name].state for p in self.providers}
        raise AllProvidersDown(
            f"All providers failed. Status: {status}. Last error: {last_error}"
        )

    def health(self) -> dict:
        return {
            p.name: {
                "state":    self.breakers[p.name].state,
                "failures": self.breakers[p.name].failure_count,
            }
            for p in self.providers
        }
```

## SSE Streaming

```python
async def stream_chat(messages, gateway, registry, executor, memory_engine):
    context = await memory_engine.build_context(session_id, message)
    msgs = build_messages(context, message)

    async def generate():
        while True:
            response = await gateway.complete(msgs, tools=registry.tools_for_llm)
            if not response.tool_calls:
                yield json.dumps({"type": "done", "provider": response.provider})
                return
            msgs.append(response.as_assistant_message())
            for tc in response.tool_calls:
                skill, tool_name = registry.get_skill_for_tool(tc.function.name)
                params = json.loads(tc.function.arguments)
                yield json.dumps({"type": "tool_start", "name": tc.function.name,
                                  "input": params})
                result = await executor.run(skill, tool_name, params)
                yield json.dumps({"type": "tool_result", "name": tool_name,
                                  "output": result.data, "success": result.success})
                msgs.append({"role": "tool", "tool_call_id": tc.id,
                             "content": json.dumps(result.data or {"error": result.error})})

    return EventSourceResponse(generate())
```

## Health Endpoint Response

```json
{
  "status": "healthy",
  "providers": {
    "primary":   {"state": "closed",    "failures": 0},
    "fallback":  {"state": "closed",    "failures": 0},
    "secondary": {"state": "open",      "failures": 3},
    "tertiary":  {"state": "half_open", "failures": 3}
  },
  "memory": {
    "core_tokens": 847,
    "episodic_count": 1243
  },
  "skills": {
    "loaded": 6,
    "healthy": 6
  },
  "scheduler": {
    "jobs": 5,
    "running": 0
  }
}
```
