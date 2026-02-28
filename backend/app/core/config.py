"""Pydantic BaseSettings with secrets_dir loading."""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _project_root() -> Path:
    """Project root (parent of backend/)."""
    return Path(__file__).resolve().parents[3]


def _secrets_dir() -> Path:
    """Path to config/secrets/ from project root."""
    return _project_root() / "config" / "secrets"


class TalonSettings(BaseSettings):
    """Application settings loaded from env and config/secrets/."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        secrets_dir=str(_secrets_dir()),
        extra="ignore",
    )

    # Application
    log_level: str = Field(default="INFO", description="Logging level")
    debug: bool = Field(default=False, description="Debug mode")
    allowed_origins: list[str] = Field(
        default=["http://localhost:5173", "http://localhost:3000"],
        description="CORS allowed origins",
    )
    rate_limit_default: int = Field(default=100, description="Default requests per minute per IP")
    rate_limit_llm: int = Field(default=20, description="LLM endpoint requests per minute per IP")

    # Database — password from config/secrets/db_password
    db_host: str = Field(default="127.0.0.1", description="PostgreSQL host")
    db_port: int = Field(default=5432, description="PostgreSQL port")
    db_name: str = Field(default="talon", description="PostgreSQL database name")
    db_user: str = Field(default="talon", description="PostgreSQL user")
    db_password: str = Field(default="", description="PostgreSQL password (from secrets)")

    @property
    def db_url_sync(self) -> str:
        """Synchronous database URL for Alembic."""
        return (
            f"postgresql://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    @property
    def db_url_async(self) -> str:
        """Async database URL for SQLAlchemy."""
        return (
            f"postgresql+asyncpg://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    @property
    def project_root(self) -> Path:
        """Project root (parent of backend/)."""
        return _project_root()

    @property
    def log_file_path(self) -> Path:
        """Path to structured log file."""
        return self.project_root / "data" / "logs" / "talon.jsonl"

    @property
    def memories_dir(self) -> Path:
        """Directory containing Markdown memory source files."""
        return self.project_root / "data" / "memories"

    @property
    def core_matrix_path(self) -> Path:
        """Path to compiled core matrix JSON (output of compressor)."""
        return self.project_root / "data" / "core_matrix.json"

    # ntfy push notifications — all optional; client is disabled if url or topic absent.
    # Auth: supply either (ntfy_username + ntfy_password) for Basic auth, or ntfy_token for Bearer.
    # Basic auth takes precedence when both are present.
    ntfy_url: str = Field(default="", description="ntfy server base URL (from secrets)")
    ntfy_topic: str = Field(default="", description="ntfy topic name (from secrets)")
    ntfy_username: str = Field(default="", description="ntfy Basic-auth username (from secrets)")
    ntfy_password: str = Field(default="", description="ntfy Basic-auth password (from secrets)")
    ntfy_token: str = Field(default="", description="ntfy Bearer token (from secrets; used when no username/password)")

    @property
    def personas_config_path(self) -> Path:
        """Path to persona definitions."""
        return self.project_root / "config" / "personas.yaml"

    @property
    def skills_dir(self) -> Path:
        """Directory containing skill subdirectories (skill.toml + main.py)."""
        return self.project_root / "backend" / "skills"

    @property
    def ntfy_configured(self) -> bool:
        """True when both ntfy_url and ntfy_topic are set."""
        return bool(self.ntfy_url and self.ntfy_topic)


_settings: TalonSettings | None = None


def get_settings() -> TalonSettings:
    """Return cached settings instance, initializing if needed.

    In normal app startup, `init_settings` is called first. Tests and
    scripts may call `get_settings` directly, so we lazily initialize
    here as well to satisfy the non-None contract.
    """
    global _settings
    if _settings is None:
        _settings = TalonSettings()
    return _settings


def init_settings() -> TalonSettings:
    """Initialize and cache settings. Called at startup."""
    global _settings
    _settings = TalonSettings()
    return _settings
