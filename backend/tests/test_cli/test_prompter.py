"""Tests for WizardPrompter protocol and ScriptedPrompter."""

import pytest
from app.cli.prompter import ScriptedPrompter


class TestScriptedPrompter:
    """ScriptedPrompter returns pre-set answers in order."""

    def test_select_returns_string(self) -> None:
        p = ScriptedPrompter(["quickstart"])
        assert p.select("mode", ["quickstart", "advanced"]) == "quickstart"

    def test_text_returns_string(self) -> None:
        p = ScriptedPrompter(["my_password"])
        assert p.text("password") == "my_password"

    def test_confirm_returns_bool(self) -> None:
        p = ScriptedPrompter([True, False])
        assert p.confirm("yes?") is True
        assert p.confirm("no?") is False

    def test_intro_outro_recorded(self) -> None:
        p = ScriptedPrompter([])
        p.intro("Title", "Message")
        p.outro("Done")
        assert "intro:Title" in p.messages
        assert "outro:Done" in p.messages

    def test_note_recorded(self) -> None:
        p = ScriptedPrompter([])
        p.note("something")
        assert "note:something" in p.messages

    def test_progress_recorded(self) -> None:
        p = ScriptedPrompter([])
        p.progress("loading")
        assert "progress:loading" in p.messages

    def test_exhausted_raises_index_error(self) -> None:
        p = ScriptedPrompter([])
        with pytest.raises(IndexError, match="ran out of answers"):
            p.select("x", ["a", "b"])

    def test_wrong_type_for_select_raises(self) -> None:
        p = ScriptedPrompter([True])
        with pytest.raises(TypeError, match="Expected str"):
            p.select("x", ["a", "b"])

    def test_wrong_type_for_confirm_raises(self) -> None:
        p = ScriptedPrompter(["not_a_bool"])
        with pytest.raises(TypeError, match="Expected bool"):
            p.confirm("y/n?")
