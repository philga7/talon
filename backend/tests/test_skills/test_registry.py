"""SkillRegistry tests: scan, load, namespace."""

from pathlib import Path

import pytest
from app.skills.registry import TOOL_NAMESPACE_SEP, SkillRegistry


def test_registry_scan_discovers_skills() -> None:
    """Scan finds skill dirs with skill.toml + main.py."""
    # Use real backend/skills dir (run from backend/)
    root = Path(__file__).resolve().parents[2]  # backend
    skills_dir = root / "skills"
    if not skills_dir.is_dir():
        pytest.skip("backend/skills not present")
    registry = SkillRegistry(skills_dir)
    n = registry.scan()
    assert n >= 2  # searxng_search, yahoo_finance
    names = [s["name"] for s in registry.list_skills()]
    assert "searxng_search" in names
    assert "yahoo_finance" in names


def test_registry_tools_are_namespaced() -> None:
    """Tools for LLM have namespaced names (skill__tool)."""
    root = Path(__file__).resolve().parents[2]
    skills_dir = root / "skills"
    if not skills_dir.is_dir():
        pytest.skip("backend/skills not present")
    registry = SkillRegistry(skills_dir)
    registry.scan()
    tools = registry.tools_for_llm()
    names = [t["function"]["name"] for t in tools]
    assert any(n.startswith("searxng_search" + TOOL_NAMESPACE_SEP) for n in names)
    assert any(n.startswith("yahoo_finance" + TOOL_NAMESPACE_SEP) for n in names)


def test_registry_resolve_returns_skill_and_tool() -> None:
    """Resolve namespaced name to (skill, tool_name)."""
    root = Path(__file__).resolve().parents[2]
    skills_dir = root / "skills"
    if not skills_dir.is_dir():
        pytest.skip("backend/skills not present")
    registry = SkillRegistry(skills_dir)
    registry.scan()
    resolved = registry.resolve("searxng_search__search")
    assert resolved is not None
    skill, tool_name = resolved
    assert skill.name == "searxng_search"
    assert tool_name == "search"
    assert registry.resolve("unknown__tool") is None


def test_registry_resolve_single_underscore_alias() -> None:
    """Resolve accepts provider-normalized name (skill_tool) as alias of skill__tool."""
    root = Path(__file__).resolve().parents[2]
    skills_dir = root / "skills"
    if not skills_dir.is_dir():
        pytest.skip("backend/skills not present")
    registry = SkillRegistry(skills_dir)
    registry.scan()
    resolved = registry.resolve("searxng_search_search")
    assert resolved is not None
    skill, tool_name = resolved
    assert skill.name == "searxng_search"
    assert tool_name == "search"


def test_registry_resolve_skill_name_only_single_tool() -> None:
    """Resolve accepts bare skill name when that skill has exactly one tool (LLM omits tool)."""
    root = Path(__file__).resolve().parents[2]
    skills_dir = root / "skills"
    if not skills_dir.is_dir():
        pytest.skip("backend/skills not present")
    registry = SkillRegistry(skills_dir)
    registry.scan()
    resolved = registry.resolve("searxng_search")
    assert resolved is not None
    skill, tool_name = resolved
    assert skill.name == "searxng_search"
    assert tool_name == "search"


def test_registry_resolve_strips_whitespace() -> None:
    """Resolve normalizes by stripping leading/trailing whitespace from the name."""
    root = Path(__file__).resolve().parents[2]
    skills_dir = root / "skills"
    if not skills_dir.is_dir():
        pytest.skip("backend/skills not present")
    registry = SkillRegistry(skills_dir)
    registry.scan()
    resolved = registry.resolve("  searxng_search__search  ")
    assert resolved is not None
    skill, tool_name = resolved
    assert skill.name == "searxng_search"
    assert tool_name == "search"


def test_registry_empty_dir_returns_zero() -> None:
    """Scan of dir with no skill dirs returns 0."""
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        registry = SkillRegistry(Path(d))
        n = registry.scan()
    assert n == 0
    assert registry.list_skills() == []
