"""EventRouter dispatch logic tests — test the handler, not OS events."""
# pyright: reportPrivateUsage=false, reportAttributeAccessIssue=false

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from app.personas.registry import PersonaConfig
from app.sentinel.tree import EventRouter


@pytest.fixture
def router(tmp_path: Path) -> EventRouter:
    memories_dir = tmp_path / "memories"
    skills_dir = tmp_path / "skills"
    config_dir = tmp_path / "config"
    for d in (memories_dir, skills_dir, config_dir):
        d.mkdir()
    memory = MagicMock()
    memory.recompile_persona.return_value = {"schema": [], "rows": []}
    registry = AsyncMock()
    registry.load_all = AsyncMock(return_value=2)
    personas = MagicMock()
    personas.get.return_value = PersonaConfig(id="main", memories_dir=memories_dir)
    r = EventRouter(
        memory=memory,
        registry=registry,
        memories_dir=memories_dir,
        skills_dir=skills_dir,
        config_dir=config_dir,
        persona_registry=personas,
    )
    return r


class TestDispatchRouting:
    @pytest.mark.asyncio
    async def test_memory_file_triggers_recompile(self, router: EventRouter, tmp_path: Path) -> None:
        loop = asyncio.get_running_loop()
        router.bind_loop(loop)
        memory_file = str(tmp_path / "memories" / "identity.md")
        router.dispatch("modified", memory_file)
        await asyncio.sleep(0.1)
        router._memory.recompile_persona.assert_called_once()

    @pytest.mark.asyncio
    async def test_skill_file_triggers_reload(self, router: EventRouter, tmp_path: Path) -> None:
        loop = asyncio.get_running_loop()
        router.bind_loop(loop)
        skill_file = str(tmp_path / "skills" / "my_skill" / "main.py")
        router.dispatch("modified", skill_file)
        await asyncio.sleep(0.1)
        router._registry.load_all.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_config_file_dispatches_without_crash(self, router: EventRouter, tmp_path: Path) -> None:
        loop = asyncio.get_running_loop()
        router.bind_loop(loop)
        config_file = str(tmp_path / "config" / "providers.yaml")
        router.dispatch("modified", config_file)
        await asyncio.sleep(0.1)

    @pytest.mark.asyncio
    async def test_unrelated_path_is_ignored(self, router: EventRouter, tmp_path: Path) -> None:
        loop = asyncio.get_running_loop()
        router.bind_loop(loop)
        router.dispatch("modified", "/tmp/random_file.txt")
        await asyncio.sleep(0.1)
        router._memory.recompile_persona.assert_not_called()
        router._registry.load_all.assert_not_awaited()

    def test_dispatch_without_loop_is_noop(self, router: EventRouter, tmp_path: Path) -> None:
        memory_file = str(tmp_path / "memories" / "identity.md")
        router.dispatch("modified", memory_file)
        router._memory.recompile_persona.assert_not_called()

    @pytest.mark.asyncio
    async def test_recompile_failure_is_logged_not_raised(self, router: EventRouter, tmp_path: Path) -> None:
        loop = asyncio.get_running_loop()
        router.bind_loop(loop)
        router._memory.recompile_persona.side_effect = RuntimeError("disk full")
        memory_file = str(tmp_path / "memories" / "identity.md")
        router.dispatch("modified", memory_file)
        await asyncio.sleep(0.1)
