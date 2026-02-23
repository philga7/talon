"""LLM gateway with circuit breaker, retry, and LiteLLM integration."""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

import litellm
import yaml  # type: ignore[reportMissingModuleSource]
from structlog import get_logger

from app.core.config import TalonSettings
from app.core.errors import AllProvidersDown
from app.llm.circuit_breaker import CircuitBreaker
from app.llm.models import LLMRequest, LLMResponse, ProviderConfig, ProviderStatus
from app.llm.retry import retry_async

log = get_logger()


class LLMGateway:
    """Resilient LLM gateway with fallback chain over multiple providers."""

    def __init__(
        self,
        providers: list[ProviderConfig],
        *,
        failure_threshold: int = 3,
        recovery_timeout: float = 60.0,
    ) -> None:
        if not providers:
            msg = "At least one provider must be configured for LLMGateway"
            raise ValueError(msg)

        self._providers = providers
        self._breakers: dict[str, CircuitBreaker] = {
            p.name: CircuitBreaker(
                name=p.name,
                failure_threshold=failure_threshold,
                recovery_timeout=recovery_timeout,
            )
            for p in providers
        }

    @property
    def providers(self) -> list[ProviderConfig]:
        return list(self._providers)

    def get_provider_statuses(self) -> list[ProviderStatus]:
        """Return current circuit breaker status for all providers."""
        statuses: list[ProviderStatus] = []
        for cfg in self._providers:
            breaker = self._breakers[cfg.name]
            statuses.append(
                ProviderStatus(
                    name=cfg.name,
                    state=breaker.current_state(),
                    failure_count=breaker.failure_count,
                    opened_seconds_ago=breaker.opened_seconds_ago(),
                ),
            )
        return statuses

    async def complete(self, request: LLMRequest) -> LLMResponse:
        """Call the first healthy provider in the chain and return a response.

        This method applies per-provider circuit breaker logic and retry
        semantics. If all providers are unavailable, AllProvidersDown is raised.
        """
        last_error: BaseException | None = None

        for provider in self._providers:
            breaker = self._breakers[provider.name]
            if not breaker.can_attempt():
                continue

            try:
                async def _op(provider_config: ProviderConfig = provider) -> LLMResponse:
                    return await self._call_provider(provider_config, request)

                response = await retry_async(
                    _op,
                    max_attempts=provider.max_retries,
                )
            except BaseException as exc:  # noqa: BLE001 - deliberate catch
                breaker.record_failure()
                last_error = exc
                log.warning(
                    "llm_provider_error",
                    provider=provider.name,
                    model=provider.model,
                    error=str(exc),
                )
                continue

            breaker.record_success()
            return response

        log.error(
            "all_providers_down",
            last_error=str(last_error) if last_error else None,
        )
        raise AllProvidersDown()

    async def stream(self, request: LLMRequest) -> AsyncGenerator[str, None]:
        """Stream tokens from the first healthy provider in the chain.

        This is a minimal streaming abstraction for Phase 2. Higher-level
        SSE event typing is handled at the API layer.
        """
        # For now, we simply delegate to the same provider selection logic as
        # complete(), but with stream-enabled calls.
        for provider in self._providers:
            breaker = self._breakers[provider.name]
            if not breaker.can_attempt():
                continue

            try:
                async for chunk in self._stream_from_provider(provider, request):
                    yield chunk
                breaker.record_success()
                return
            except BaseException as exc:  # noqa: BLE001 - deliberate catch
                breaker.record_failure()
                log.warning(
                    "llm_provider_stream_error",
                    provider=provider.name,
                    model=provider.model,
                    error=str(exc),
                )
                continue

        log.error("all_providers_down_stream")
        raise AllProvidersDown()

    async def _call_provider(
        self,
        provider: ProviderConfig,
        request: LLMRequest,
    ) -> LLMResponse:
        """Invoke a single provider via LiteLLM and normalize the response."""
        api_key = os.getenv(provider.api_key_env, "")
        litellm_params: dict[str, Any] = {
            "model": provider.model,
            "messages": [m.model_dump() for m in request.messages],
            "temperature": request.temperature,
        }
        if request.max_tokens is not None:
            litellm_params["max_tokens"] = request.max_tokens

        # LiteLLM reads API keys from env vars; we keep explicit here to make
        # tests simpler, but do not log the key.
        response = await litellm.acompletion(api_key=api_key, **litellm_params)

        # The exact OpenAI-compatible shape is documented by LiteLLM; we only
        # rely on the minimal fields we need here.
        choices = response.get("choices") or []
        if not choices:
            msg = f"Provider {provider.name} returned no choices"
            raise RuntimeError(msg)

        message = choices[0]["message"]
        content = message.get("content") or ""

        usage = response.get("usage") or {}
        tokens = {
            "prompt_tokens": int(usage.get("prompt_tokens") or 0),
            "completion_tokens": int(usage.get("completion_tokens") or 0),
            "total_tokens": int(usage.get("total_tokens") or 0),
        }

        return LLMResponse(
            content=content,
            provider=provider.name,
            tool_calls=message.get("tool_calls"),
            tokens=tokens,
        )

    async def _stream_from_provider(
        self,
        provider: ProviderConfig,
        request: LLMRequest,
    ) -> AsyncGenerator[str, None]:
        """Invoke a single provider via LiteLLM in streaming mode."""
        api_key = os.getenv(provider.api_key_env, "")
        litellm_params: dict[str, Any] = {
            "model": provider.model,
            "messages": [m.model_dump() for m in request.messages],
            "temperature": request.temperature,
            "stream": True,
        }
        if request.max_tokens is not None:
            litellm_params["max_tokens"] = request.max_tokens

        async for chunk in litellm.acompletion(api_key=api_key, **litellm_params):
            # LiteLLM streams OpenAI-style ChatCompletionChunk objects.
            choices = getattr(chunk, "choices", None) or chunk.get("choices") or []
            if not choices:
                continue
            delta = choices[0].get("delta") or {}
            content_piece = delta.get("content")
            if content_piece:
                yield content_piece


def _providers_yaml_path(settings: TalonSettings) -> Path:
    return settings.project_root / "config" / "providers.yaml"


def load_provider_configs(settings: TalonSettings) -> list[ProviderConfig]:
    """Load ProviderConfig entries from config/providers.yaml."""
    path = _providers_yaml_path(settings)
    if not path.exists():
        msg = f"providers.yaml not found at {path}"
        raise FileNotFoundError(msg)

    with path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    providers_raw = raw.get("providers") or []
    providers: list[ProviderConfig] = []
    for item in providers_raw:
        providers.append(ProviderConfig.model_validate(item))
    return providers


def create_gateway(settings: TalonSettings) -> LLMGateway:
    """Factory for constructing the LLMGateway from settings + config file."""
    providers = load_provider_configs(settings)
    return LLMGateway(providers=providers)

