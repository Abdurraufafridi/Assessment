"""Errors raised by agent orchestration."""

from app.domain.errors import DomainError


class IntakeAgentError(DomainError):
    """Base exception for intake-agent failures."""


class IntakeRequestError(IntakeAgentError):
    """Raised when an intake request is empty or unusably large."""


class InvalidIntakeOutputError(IntakeAgentError):
    """Raised when LLM output is not valid intake JSON or fails validation."""


class ResearchAgentError(DomainError):
    """Base exception for research-agent failures."""


class ResearchRequestError(ResearchAgentError):
    """Raised when research cannot start from the available workflow state."""


class InvalidResearchOutputError(ResearchAgentError):
    """Raised when research output is malformed or cites unavailable evidence."""


class PlanningAgentError(DomainError):
    """Base exception for planning-agent failures."""


class PlanningRequestError(PlanningAgentError):
    """Raised when planning lacks the research required to proceed."""


class InvalidPlanningOutputError(PlanningAgentError):
    """Raised when an outline is malformed or cites unavailable evidence."""


class WritingAgentError(DomainError):
    """Base exception for writing-agent failures."""


class WritingRequestError(WritingAgentError):
    """Raised when writing lacks approved research or an approved outline."""


class InvalidWritingOutputError(WritingAgentError):
    """Raised when a draft is malformed or violates citation requirements."""
