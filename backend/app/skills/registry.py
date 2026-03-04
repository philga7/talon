"""Skill registry: scan directory, dynamic import, namespace tools for LiteLLM."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import structlog
import tomli

from app.skills.base import BaseSkill

log = structlog.get_logger()

# Namespace separator for tool names in LiteLLM (skill_name__tool_name)
TOOL_NAMESPACE_SEP = "__"


def _load_toml(path: Path) -> dict[str, Any] | None:
    """Load skill.toml; return None if missing or invalid."""
    if not path.exists():
        return None
    try:
        return tomli.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomli.TOMLDecodeError) as e:
        log.warning("skill_toml_load_failed", path=str(path), error=str(e))
        return None


def _skill_enabled(meta: dict[str, Any]) -> bool:
    """True if [skill] enabled is not False."""
    skill = meta.get("skill") or {}
    return skill.get("enabled", True) is not False


def _discover_skill_dirs(skills_dir: Path) -> list[Path]:
    """Return sorted list of skill directories (each has skill.toml + main.py)."""
    if not skills_dir.is_dir():
        return []
    dirs: list[Path] = []
    for entry in skills_dir.iterdir():
        if not entry.is_dir():
            continue
        if (entry / "skill.toml").exists() and (entry / "main.py").exists():
            dirs.append(entry)
    return sorted(dirs)


def _import_skill_module(skill_dir: Path) -> BaseSkill | None:
    """Load skill module from main.py and return the skill instance."""
    main_py = skill_dir / "main.py"
    if not main_py.exists():
        return None
    spec = importlib.util.spec_from_file_location(
        f"skill_{skill_dir.name}",
        main_py,
        submodule_search_locations=[str(skill_dir)],
    )
    if spec is None or spec.loader is None:
        log.warning("skill_spec_failed", path=str(main_py))
        return None
    try:
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    except Exception as e:  # noqa: BLE001 - log and skip bad skills
        log.warning("skill_import_failed", path=str(main_py), error=str(e))
        return None
    # Find first BaseSkill subclass instance (e.g. exported as "skill" or single class)
    for name in dir(module):
        if name.startswith("_"):
            continue
        obj = getattr(module, name)
        if isinstance(obj, BaseSkill):
            return obj
    log.warning("skill_no_instance", path=str(main_py))
    return None


class SkillRegistry:
    """Scans a skills directory, loads skills, and exposes namespaced tools for the LLM."""

    def __init__(self, skills_dir: Path) -> None:
        self._skills_dir = skills_dir
        self._skills: list[BaseSkill] = []
        self._tools_for_llm: list[dict[str, Any]] = []
        self._tool_to_skill: dict[
            str, tuple[BaseSkill, str]
        ] = {}  # namespaced_name -> (skill, tool_name)

    def scan(self) -> int:
        """Load all skills from skills_dir. Returns count of loaded skills."""
        self._skills.clear()
        self._tools_for_llm.clear()
        self._tool_to_skill.clear()
        for skill_dir in _discover_skill_dirs(self._skills_dir):
            meta = _load_toml(skill_dir / "skill.toml")
            if meta is None or not _skill_enabled(meta):
                continue
            skill = _import_skill_module(skill_dir)
            if skill is None:
                continue
            # Ensure name matches directory
            expected_name = skill_dir.name
            if skill.name and skill.name != expected_name:
                skill.name = expected_name
            elif not skill.name:
                skill.name = expected_name
            self._skills.append(skill)
            for tool in skill.tools:
                ns_name = f"{skill.name}{TOOL_NAMESPACE_SEP}{tool.name}"
                self._tool_to_skill[ns_name] = (skill, tool.name)
                # Some providers normalize "skill__tool" to "skill_tool"; register alias.
                alias = f"{skill.name}_{tool.name}"
                if alias != ns_name:
                    self._tool_to_skill[alias] = (skill, tool.name)
                params = dict(tool.parameters)
                if tool.required:
                    params["required"] = tool.required
                self._tools_for_llm.append(
                    {
                        "type": "function",
                        "function": {
                            "name": ns_name,
                            "description": tool.description,
                            "parameters": params,
                        },
                    }
                )
        return len(self._skills)

    async def load_all(self) -> int:
        """Scan and call on_load for each skill. Returns count of loaded skills."""
        n = self.scan()
        for skill in self._skills:
            try:
                await skill.on_load()
            except Exception as e:  # noqa: BLE001
                log.warning("skill_on_load_failed", skill=skill.name, error=str(e))
        return n

    def tools_for_llm(self) -> list[dict[str, Any]]:
        """OpenAI-style tools list for LiteLLM (only from healthy skills)."""
        healthy = [s for s in self._skills if s.health_check()]
        result: list[dict[str, Any]] = []
        for t in self._tools_for_llm:
            name = t["function"]["name"]
            skill_name = name.split(TOOL_NAMESPACE_SEP, 1)[0]
            if any(s.name == skill_name for s in healthy):
                result.append(t)
        return result

    def resolve(self, namespaced_tool_name: str) -> tuple[BaseSkill, str] | None:
        """Return (skill, tool_name) for the namespaced tool name, or None."""
        resolved = self._tool_to_skill.get(namespaced_tool_name)
        if resolved is not None:
            return resolved
        # Fallback: some LLM providers return "skill_tool" instead of "skill__tool".
        fallback = namespaced_tool_name.replace(TOOL_NAMESPACE_SEP, "_", 1)
        return self._tool_to_skill.get(fallback)

    def list_skills(self) -> list[dict[str, Any]]:
        """List loaded skills with name, version, tool count."""
        return [
            {
                "name": s.name,
                "version": getattr(s, "version", "0.0.0"),
                "tools": [t.name for t in s.tools],
                "healthy": s.health_check(),
            }
            for s in self._skills
        ]
