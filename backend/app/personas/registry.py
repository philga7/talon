"""Persona config loader and channel-binding resolver."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import structlog
import yaml  # type: ignore[reportMissingModuleSource]

log = structlog.get_logger()


@dataclass(frozen=True)
class PersonaConfig:
    """Resolved persona configuration."""

    id: str
    memories_dir: Path
    model_override: str | None = None


class PersonaRegistry:
    """Loads personas.yaml and resolves persona by id or channel binding."""

    def __init__(self, config_path: Path, project_root: Path) -> None:
        self._config_path = config_path
        self._project_root = project_root
        self._personas: dict[str, PersonaConfig] = {}
        self._channel_map: dict[tuple[str, str], str] = {}
        self.reload()

    def reload(self) -> None:
        """Reload persona definitions from config file."""
        raw = self._read_raw_config()
        personas_block = raw.get("personas", {})
        self._personas = {}
        self._channel_map = {}

        for persona_id, cfg in personas_block.items():
            if not isinstance(cfg, dict):
                continue
            memories_dir_raw = str(cfg.get("memories_dir", f"data/memories/{persona_id}"))
            model_override = cfg.get("model_override")
            resolved_memories_dir = (self._project_root / memories_dir_raw).resolve()
            persona = PersonaConfig(
                id=persona_id,
                memories_dir=resolved_memories_dir,
                model_override=str(model_override) if model_override else None,
            )
            self._personas[persona_id] = persona

            bindings = cfg.get("channel_bindings", [])
            if isinstance(bindings, list):
                for item in bindings:
                    if not isinstance(item, dict):
                        continue
                    platform = str(item.get("platform", "")).strip().lower()
                    channel_id = str(item.get("channel_id", "")).strip()
                    if platform and channel_id:
                        self._channel_map[(platform, channel_id)] = persona_id

        if "main" not in self._personas:
            fallback_dir = (self._project_root / "data" / "memories" / "main").resolve()
            if not fallback_dir.is_dir():
                fallback_dir = (self._project_root / "data" / "memories").resolve()
            self._personas["main"] = PersonaConfig(id="main", memories_dir=fallback_dir)

    def get(self, persona_id: str) -> PersonaConfig:
        """Resolve by explicit persona id; fallback to main."""
        return self._personas.get(persona_id, self._personas["main"])

    def resolve(self, platform: str, channel_id: str) -> PersonaConfig:
        """Resolve by platform/channel binding; fallback to main."""
        key = (platform.strip().lower(), channel_id.strip())
        persona_id = self._channel_map.get(key, "main")
        return self.get(persona_id)

    def all_personas(self) -> dict[str, PersonaConfig]:
        """Return a copy of all persona configs."""
        return dict(self._personas)

    def _read_raw_config(self) -> dict:
        if not self._config_path.is_file():
            log.info("personas_config_missing", path=str(self._config_path))
            return {}
        try:
            data = yaml.safe_load(self._config_path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:
            log.warning("personas_config_parse_failed", path=str(self._config_path), error=str(exc))
            return {}
        return data if isinstance(data, dict) else {}
