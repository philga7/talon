"""Integration manager: lifecycle and chat callback wiring for all integrations."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession
from structlog import get_logger

from app.integrations.base import BaseIntegration, IntegrationStatus
from app.personas.registry import PersonaRegistry

log = get_logger()


class IntegrationManager:
    """Manages lifecycle of all registered integrations."""

    def __init__(self) -> None:
        self._integrations: list[BaseIntegration] = []

    def register(self, integration: BaseIntegration) -> None:
        self._integrations.append(integration)

    async def start_all(self) -> None:
        """Start all configured integrations. Unconfigured ones are skipped."""
        for integ in self._integrations:
            if integ.is_configured():
                try:
                    await integ.start()
                    log.info("integration_started", name=integ.name)
                except Exception:
                    log.exception("integration_start_failed", name=integ.name)
            else:
                log.info("integration_skipped_not_configured", name=integ.name)

    async def stop_all(self) -> None:
        """Stop all integrations."""
        for integ in self._integrations:
            try:
                await integ.stop()
            except Exception:
                log.exception("integration_stop_failed", name=integ.name)

    def statuses(self) -> list[IntegrationStatus]:
        return [integ.status() for integ in self._integrations]

    @property
    def integrations(self) -> list[BaseIntegration]:
        return list(self._integrations)


async def make_chat_callback(
    *,
    get_db_session: object,
    gateway: object,
    memory: object,
    registry: object,
    executor: object,
    persona_registry: PersonaRegistry,
) -> object:
    """Build a chat callback that routes messages through the ChatRouter.

    The returned async callable has signature:
        async def callback(session_id: str, message: str, source: str, persona_id: str = "main") -> str
    """
    from app.api.chat_router import build_messages, run_tool_loop, save_turn

    async def _callback(
        session_id: str,
        message: str,
        source: str,
        persona_id: str = "main",
    ) -> str:
        db: AsyncSession = await get_db_session.__anext__()  # type: ignore[union-attr]
        try:
            persona = persona_registry.get(persona_id)
            messages = await build_messages(
                session_id=session_id,
                user_message=message,
                db=db,
                memory=memory,  # type: ignore[arg-type]
                persona_id=persona.id,
                persona_memories_dir=persona.memories_dir,
            )
            response = await run_tool_loop(
                messages=messages,
                gateway=gateway,  # type: ignore[arg-type]
                registry=registry,  # type: ignore[arg-type]
                executor=executor,  # type: ignore[arg-type]
                model_override=persona.model_override,
            )
            reply = response.content or ""
            await save_turn(
                db=db,
                session_id=session_id,
                user_message=message,
                assistant_message=reply,
                memory=memory,  # type: ignore[arg-type]
                persona_id=persona.id,
            )
            await db.commit()
            return reply
        except Exception:
            await db.rollback()
            log.exception("integration_chat_callback_failed", session_id=session_id)
            raise
        finally:
            await db.close()

    return _callback
