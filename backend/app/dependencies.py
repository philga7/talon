"""FastAPI dependency injection."""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import TalonSettings
from app.llm.gateway import LLMGateway, create_gateway
from app.memory.compressor import MemoryCompressor
from app.memory.engine import MemoryEngine
from app.memory.episodic import EpisodicStore
from app.memory.working import WorkingMemoryStore

# Engine and session factory — initialized at startup
_engine = None
_async_session_factory: async_sessionmaker[AsyncSession] | None = None

# LLM gateway — initialized at startup
_gateway: LLMGateway | None = None

# Memory engine — initialized at startup (Phase 3)
_memory: MemoryEngine | None = None


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


async def get_registry() -> None:
    """Skill registry (Phase 4). Stub returns None."""
    return None


async def get_scheduler() -> None:
    """Scheduler (Phase 6). Stub returns None."""
    return None
