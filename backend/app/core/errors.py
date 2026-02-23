"""Exception hierarchy for Talon."""


class TalonError(Exception):
    """Base exception for all Talon errors."""


class AllProvidersDown(TalonError):  # noqa: N818 - name matches plan/arch docs
    """All LLM providers are unavailable (circuit breakers open)."""


class SkillExecutionError(TalonError):
    """A skill failed during execution."""


class MemoryCompilerError(TalonError):
    """Memory compilation (Markdown → matrix) failed."""


class SecurityError(TalonError):
    """Authentication, authorization, or input validation failed."""
