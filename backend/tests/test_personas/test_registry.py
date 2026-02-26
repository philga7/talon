"""PersonaRegistry resolution tests."""

from pathlib import Path

from app.personas.registry import PersonaRegistry


def test_resolve_channel_binding(tmp_path: Path) -> None:
    config = tmp_path / "config" / "personas.yaml"
    config.parent.mkdir(parents=True)
    config.write_text(
        "personas:\n"
        "  main:\n"
        "    memories_dir: data/memories/main\n"
        "    model_override: null\n"
        "    channel_bindings: []\n"
        "  analyst:\n"
        "    memories_dir: data/memories/analyst\n"
        "    model_override: null\n"
        "    channel_bindings:\n"
        "      - platform: slack\n"
        '        channel_id: "C123"\n',
        encoding="utf-8",
    )
    registry = PersonaRegistry(config_path=config, project_root=tmp_path)
    resolved = registry.resolve("slack", "C123")
    assert resolved.id == "analyst"
    assert resolved.memories_dir == (tmp_path / "data" / "memories" / "analyst").resolve()


def test_get_falls_back_to_main_for_unknown_persona(tmp_path: Path) -> None:
    config = tmp_path / "config" / "personas.yaml"
    config.parent.mkdir(parents=True)
    config.write_text(
        "personas:\n"
        "  main:\n"
        "    memories_dir: data/memories/main\n"
        "    model_override: null\n"
        "    channel_bindings: []\n",
        encoding="utf-8",
    )
    registry = PersonaRegistry(config_path=config, project_root=tmp_path)
    resolved = registry.get("does-not-exist")
    assert resolved.id == "main"


def test_resolve_falls_back_to_main_for_unknown_channel(tmp_path: Path) -> None:
    config = tmp_path / "config" / "personas.yaml"
    config.parent.mkdir(parents=True)
    config.write_text(
        "personas:\n"
        "  main:\n"
        "    memories_dir: data/memories/main\n"
        "    model_override: null\n"
        "    channel_bindings: []\n",
        encoding="utf-8",
    )
    registry = PersonaRegistry(config_path=config, project_root=tmp_path)
    resolved = registry.resolve("discord", "unknown")
    assert resolved.id == "main"
