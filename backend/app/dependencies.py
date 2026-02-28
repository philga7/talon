"""FastAPI dependency injection."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import TalonSettings
from app.integrations.manager import IntegrationManager
from app.llm.gateway import LLMGateway, create_gateway
from app.memory.compressor import MemoryCompressor
from app.memory.engine import MemoryEngine
from app.memory.episodic import EpisodicStore
from app.memory.working import WorkingMemoryStore
from app.notifications.ntfy import NtfyClient
from app.personas.registry import PersonaRegistry
from app.scheduler.engine import TalonScheduler
from app.sentinel.tree import EventRouter
from app.sentinel.watcher import FileSentinel
from app.skills.executor import SkillExecutor
from app.skills.registry import SkillRegistry

# Engine and session factory — initialized at startup
_engine = None
_async_session_factory: async_sessionmaker[AsyncSession] | None = None

# LLM gateway — initialized at startup
_gateway: LLMGateway | None = None

# Memory engine — initialized at startup (Phase 3)
_memory: MemoryEngine | None = None

# Skill registry and executor — initialized at startup (Phase 4)
_registry: SkillRegistry | None = None
_executor: SkillExecutor | None = None

# Scheduler and sentinel — initialized at startup (Phase 6)
_scheduler: TalonScheduler | None = None
_sentinel: FileSentinel | None = None
_event_router: EventRouter | None = None

# Integration manager — initialized at startup (Phase 7)
_integration_manager: IntegrationManager | None = None

# ntfy push notification client — initialized at startup (optional)
_ntfy_client: NtfyClient | None = None

# Persona registry — initialized at startup
_persona_registry: PersonaRegistry | None = None


def init_db(settings: object) -> None:
    """Initialize database engine and session factory. Called at startup."""
    global _engine, _async_session_factory
    db_url = getattr(settings, "db_url_async", "")
    _engine = create_async_engine(db_url, echo=False, pool_pre_ping=True)
    _async_session_factory = async_sessionmaker(
        bind=_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )


def init_gateway(settings: TalonSettings) -> None:
    """Initialize the global LLM gateway from configuration."""
    global _gateway
    _gateway = create_gateway(settings)


def init_memory(settings: TalonSettings) -> None:
    """Initialize the memory engine (compressor, episodic, working, core matrix)."""
    global _memory
    compressor = MemoryCompressor(max_tokens=2000)
    episodic = EpisodicStore(embed_fn=None, top_k=5)
    working = WorkingMemoryStore(idle_seconds=30 * 60)
    _memory = MemoryEngine(
        compressor=compressor,
        episodic_store=episodic,
        working_store=working,
        memories_dir=settings.memories_dir,
        core_matrix_path=settings.core_matrix_path,
    )


def init_persona_registry(settings: TalonSettings) -> PersonaRegistry:
    """Initialize persona registry from config/personas.yaml."""
    global _persona_registry
    _persona_registry = PersonaRegistry(
        config_path=settings.personas_config_path,
        project_root=settings.project_root,
    )
    return _persona_registry


def init_registry(settings: TalonSettings) -> None:
    """Initialize the skill registry and executor (Phase 4). Scan loads skills sync; on_load runs in load_registry_skills()."""
    global _registry, _executor
    _registry = SkillRegistry(settings.skills_dir)
    _registry.scan()
    _executor = SkillExecutor()


async def load_registry_skills() -> None:
    """Load all skills (scan + on_load). Call once at startup after init_registry."""
    if _registry is not None:
        await _registry.load_all()


async def get_registry() -> SkillRegistry:
    """Skill registry dependency."""
    if _registry is None:
        raise RuntimeError("Skill registry not initialized; call init_registry at startup")
    return _registry


def get_executor() -> SkillExecutor:
    """Skill executor dependency."""
    if _executor is None:
        raise RuntimeError("Skill executor not initialized; call init_registry at startup")
    return _executor


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async database session."""
    if _async_session_factory is None:
        raise RuntimeError("Database not initialized; call init_db at startup")
    async with _async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


def get_gateway() -> LLMGateway:
    """LLM gateway dependency."""
    if _gateway is None:
        msg = "LLM gateway not initialized; call init_gateway at startup"
        raise RuntimeError(msg)
    return _gateway


def get_memory() -> MemoryEngine:
    """Memory engine dependency."""
    if _memory is None:
        msg = "Memory engine not initialized; call init_memory at startup"
        raise RuntimeError(msg)
    return _memory


def get_persona_registry() -> PersonaRegistry:
    """Persona registry dependency."""
    if _persona_registry is None:
        msg = "Persona registry not initialized; call init_persona_registry at startup"
        raise RuntimeError(msg)
    return _persona_registry


def init_scheduler(settings: TalonSettings) -> TalonScheduler:
    """Initialize the scheduler and register built-in jobs."""
    global _scheduler
    if _memory is None or _gateway is None:
        raise RuntimeError("Memory and gateway must be initialized before scheduler")

    from app.scheduler.jobs import register_builtin_jobs

    _scheduler = TalonScheduler()
    register_builtin_jobs(
        _scheduler,
        memory=_memory,
        gateway=_gateway,
        working=_memory.working_store,
        log_file=settings.log_file_path,
    )
    return _scheduler


def init_sentinel(settings: TalonSettings, persona_registry: PersonaRegistry) -> FileSentinel:
    """Initialize the file sentinel and event router."""
    global _sentinel, _event_router
    if _memory is None or _registry is None:
        raise RuntimeError("Memory and registry must be initialized before sentinel")

    _event_router = EventRouter(
        memory=_memory,
        registry=_registry,
        memories_dir=settings.memories_dir,
        skills_dir=settings.skills_dir,
        config_dir=settings.project_root / "config",
        persona_registry=persona_registry,
    )
    _event_router.bind_loop(asyncio.get_running_loop())
    _sentinel = FileSentinel(_event_router)
    _sentinel.start(
        [settings.memories_dir, settings.skills_dir, settings.project_root / "config"]
    )
    return _sentinel


def get_scheduler() -> TalonScheduler:
    """Scheduler dependency."""
    if _scheduler is None:
        raise RuntimeError("Scheduler not initialized; call init_scheduler at startup")
    return _scheduler


def get_sentinel() -> FileSentinel:
    """File sentinel dependency."""
    if _sentinel is None:
        raise RuntimeError("Sentinel not initialized; call init_sentinel at startup")
    return _sentinel


async def init_integrations(
    settings: TalonSettings,
    persona_registry: PersonaRegistry,
) -> IntegrationManager:
    """Initialize and start all configured integrations (Phase 7)."""
    global _integration_manager
    if _gateway is None or _memory is None or _registry is None or _executor is None:
        raise RuntimeError("Gateway, memory, registry, executor must be initialized first")

    from app.integrations.discord import DiscordIntegration
    from app.integrations.manager import make_chat_callback
    from app.integrations.slack import SlackIntegration
    from app.integrations.telegram import TelegramIntegration
    from app.integrations.webhook import WebhookIntegration, set_webhook_chat_callback

    chat_callback = await make_chat_callback(
        get_db_session=get_db(),
        gateway=_gateway,
        memory=_memory,
        registry=_registry,
        executor=_executor,
        persona_registry=persona_registry,
    )

    _integration_manager = IntegrationManager()
    _integration_manager.register(
        DiscordIntegration(chat_callback=chat_callback, persona_registry=persona_registry)
    )
    _integration_manager.register(
        SlackIntegration(chat_callback=chat_callback, persona_registry=persona_registry)
    )
    _integration_manager.register(
        TelegramIntegration(chat_callback=chat_callback, persona_registry=persona_registry)
    )
    _integration_manager.register(WebhookIntegration())

    set_webhook_chat_callback(chat_callback)

    await _integration_manager.start_all()
    return _integration_manager


def get_integration_manager() -> IntegrationManager:
    """Integration manager dependency."""
    if _integration_manager is None:
        raise RuntimeError("Integration manager not initialized")
    return _integration_manager


def init_ntfy(settings: TalonSettings) -> NtfyClient | None:
    """Initialize the ntfy client if configured. Returns None when unconfigured."""
    global _ntfy_client
    if not settings.ntfy_configured:
        return None
    _ntfy_client = NtfyClient(
        base_url=settings.ntfy_url,
        topic=settings.ntfy_topic,
        username=settings.ntfy_username or None,
        password=settings.ntfy_password or None,
        token=settings.ntfy_token or None,
    )
    return _ntfy_client


def get_ntfy_client() -> NtfyClient | None:
    """Return the ntfy client, or None if not configured.

    Callers must check for None before sending — ntfy is optional.
    """
    return _ntfy_client
