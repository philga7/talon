"""WizardPrompter protocol and Rich implementation for testable interactive flows."""

from __future__ import annotations

from typing import Protocol

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt


class WizardPrompter(Protocol):
    """Abstraction over interactive prompts for testability."""

    def intro(self, title: str, message: str) -> None: ...
    def outro(self, message: str) -> None: ...
    def note(self, message: str) -> None: ...
    def select(self, prompt: str, choices: list[str], default: str | None = None) -> str: ...
    def text(self, prompt: str, default: str = "") -> str: ...
    def confirm(self, prompt: str, default: bool = True) -> bool: ...
    def progress(self, message: str) -> None: ...


class RichPrompter:
    """Interactive prompter backed by Rich console I/O."""

    def __init__(self, console: Console | None = None) -> None:
        self._console = console or Console()

    def intro(self, title: str, message: str) -> None:
        self._console.print()
        self._console.print(Panel(message, title=title, border_style="cyan"))
        self._console.print()

    def outro(self, message: str) -> None:
        self._console.print()
        self._console.print(Panel(message, border_style="green"))
        self._console.print()

    def note(self, message: str) -> None:
        self._console.print(f"  [dim]>[/dim] {message}")

    def select(self, prompt: str, choices: list[str], default: str | None = None) -> str:
        choice_str = " / ".join(choices)
        result = Prompt.ask(
            f"  {prompt} [{choice_str}]",
            choices=choices,
            default=default,
            console=self._console,
        )
        return result

    def text(self, prompt: str, default: str = "") -> str:
        return Prompt.ask(f"  {prompt}", default=default or None, console=self._console)

    def confirm(self, prompt: str, default: bool = True) -> bool:
        return Confirm.ask(f"  {prompt}", default=default, console=self._console)

    def progress(self, message: str) -> None:
        self._console.print(f"  [bold cyan]...[/bold cyan] {message}")


class ScriptedPrompter:
    """Non-interactive prompter that returns pre-set answers. For testing."""

    def __init__(self, answers: list[str | bool]) -> None:
        self._answers = list(answers)
        self._idx = 0
        self.messages: list[str] = []

    def _next(self) -> str | bool:
        if self._idx >= len(self._answers):
            raise IndexError("ScriptedPrompter ran out of answers")
        val = self._answers[self._idx]
        self._idx += 1
        return val

    def intro(self, title: str, message: str) -> None:
        self.messages.append(f"intro:{title}")

    def outro(self, message: str) -> None:
        self.messages.append(f"outro:{message}")

    def note(self, message: str) -> None:
        self.messages.append(f"note:{message}")

    def select(self, prompt: str, choices: list[str], default: str | None = None) -> str:
        val = self._next()
        if not isinstance(val, str):
            raise TypeError(f"Expected str for select, got {type(val)}")
        return val

    def text(self, prompt: str, default: str = "") -> str:
        val = self._next()
        if not isinstance(val, str):
            raise TypeError(f"Expected str for text, got {type(val)}")
        return val

    def confirm(self, prompt: str, default: bool = True) -> bool:
        val = self._next()
        if not isinstance(val, bool):
            raise TypeError(f"Expected bool for confirm, got {type(val)}")
        return val

    def progress(self, message: str) -> None:
        self.messages.append(f"progress:{message}")
