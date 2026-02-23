
# Talon — Testing Strategy

## Core Principle
Everything except the LLM gateway is deterministic and fully testable in isolation.
Never call a real provider in the standard test suite.

## Test Pyramid
```
        ┌──────────────────┐
        │   E2E (5%)       │  Playwright — full browser flows
        ├──────────────────┤
        │ Integration (25%)│  pytest + httpx — real DB (rollback), mocked LLM
        ├──────────────────┤
        │   Unit (70%)     │  pytest / Vitest — pure logic, zero I/O
        └──────────────────┘
```
Target: `make test` completes in **under 60 seconds**.

## conftest.py — Core Fixtures

```python
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool
from unittest.mock import AsyncMock
from app.main import app
from app.dependencies import get_db, get_gateway
from app.llm.models import LLMResponse

TEST_DB_URL = "postgresql+asyncpg://localhost/talon_test"

@pytest.fixture
async def db_session():
    engine = create_async_engine(TEST_DB_URL, poolclass=NullPool)
    async with engine.connect() as conn:
        async with conn.begin() as tx:
            async with AsyncSession(bind=conn) as session:
                app.dependency_overrides[get_db] = lambda: session
                yield session
            await tx.rollback()

@pytest.fixture
def mock_gateway():
    gw = AsyncMock()
    gw.complete.return_value = LLMResponse(
        content="Test response", provider="primary",
        tool_calls=None, tokens={"total_tokens": 42},
    )
    app.dependency_overrides[get_gateway] = lambda: gw
    yield gw
    app.dependency_overrides.pop(get_gateway, None)

@pytest.fixture
async def client(db_session, mock_gateway):
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"X-API-Key": "test-key"}
    ) as ac:
        yield ac
```

## Gateway Tests

```python
@pytest.mark.anyio
async def test_primary_provider_success(gateway):
    with patch("app.llm.gateway.acompletion",
               return_value=build_mock_response("Hello!", "primary")):
        result = await gateway.complete([{"role": "user", "content": "hi"}])
    assert result.content == "Hello!"
    assert result.provider == "primary"

@pytest.mark.anyio
async def test_fallback_after_threshold(gateway):
    async def flaky(model, **kw):
        if "primary" in model: raise ConnectionError("down")
        return build_mock_response("Fallback!", "fallback")

    with patch("app.llm.gateway.acompletion", side_effect=flaky):
        for _ in range(3):
            try: await gateway.complete([{"role": "user", "content": "x"}])
            except: pass
        result = await gateway.complete([{"role": "user", "content": "x"}])

    assert gateway.breakers["primary"].state == "open"
    assert result.provider == "fallback"

@pytest.mark.anyio
async def test_all_providers_down_raises(gateway):
    with patch("app.llm.gateway.acompletion", side_effect=ConnectionError("down")):
        with pytest.raises(AllProvidersDown):
            await gateway.complete([{"role": "user", "content": "test"}])

@pytest.mark.anyio
async def test_circuit_breaker_recovers(gateway):
    cb = gateway.breakers["primary"]
    for _ in range(3): cb.record_failure()
    assert cb.state == "open"
    cb.last_failure_time -= 61
    assert cb.state == "half_open"
    cb.record_success()
    assert cb.state == "closed"
```

## Skills Tests

```python
@pytest.mark.anyio
async def test_executor_enforces_timeout():
    executor = SkillExecutor()
    executor.DEFAULT_TIMEOUT = 0.1
    result = await executor.run(SlowSkill(), "wait", {})
    assert result.success is False
    assert "timed out" in result.error.lower()

@pytest.mark.anyio
async def test_executor_handles_exception():
    result = await SkillExecutor().run(BrokenSkill(), "any", {})
    assert result.success is False
```

## LLM Quality Tests (Separate Suite)

```python
# Run with: make test-eval — calls real providers

@pytest.mark.llm_eval
async def test_tool_calling_invokes_correct_skill(real_gateway, registry):
    response = await real_gateway.complete(
        messages=[{"role": "user", "content": "What is the weather in Atlanta?"}],
        tools=registry.tools_for_llm,
        tool_choice="auto",
    )
    assert response.tool_calls is not None
    assert any("weather" in tc.function.name for tc in response.tool_calls)
```

## Test Commands

```makefile
test:        pytest backend -m "not llm_eval" --cov=app -q && npx vitest run
test-eval:   pytest backend -m "llm_eval" -v
test-e2e:    npx playwright test
test-chaos:  pytest backend/tests/test_llm -v -k "fallback or circuit or chaos"
test-cov:    pytest backend -m "not llm_eval" --cov=app --cov-report=html
```

## What Is Intentionally NOT Tested

| Item | Reason |
|---|---|
| LLM response quality in unit tests | Non-deterministic — use `test-eval` |
| Real provider connectivity in CI | Too slow, costs tokens, needs secrets |
| APScheduler fire timing | Test job logic, not APScheduler |
| watchdog inotify events | Test the handler, not OS event delivery |
| Docker container startup | Infrastructure, not unit-testable |
