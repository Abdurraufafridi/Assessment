"""Domain errors raised by application services."""


class DomainError(Exception):
    """Base class for expected application/domain failures."""


class EntityNotFoundError(DomainError):
    """Raised when a requested entity does not exist."""


class ReferenceConsistencyError(DomainError):
    """Raised when related records violate ownership or workflow rules."""


class InvalidStateTransitionError(DomainError):
    """Raised when a workflow, task, or execution transition is not allowed."""


class StateVersionConflictError(DomainError):
    """Raised when a workflow state update targets a stale version."""


class InvalidStateError(DomainError):
    """Raised when persisted or proposed state fails validation."""
