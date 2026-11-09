"""Shared domain enums used by persistence models and state schemas."""

from enum import StrEnum


class DocumentKind(StrEnum):
    """Business role of a stored document."""

    CLIENT_TRANSCRIPT = "client_transcript"
    PAST_PROPOSAL = "past_proposal"
    REFERENCE = "reference"
    GENERATED_PROPOSAL = "generated_proposal"
    ATTACHMENT = "attachment"


class DocumentStatus(StrEnum):
    """Lifecycle status of a document ingestion attempt."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class DocumentRole(StrEnum):
    """How a document is used within a workflow."""

    INPUT = "input"
    REFERENCE = "reference"
    DRAFT = "draft"
    OUTPUT = "output"


class WorkflowStage(StrEnum):
    """Ordered business stage of a proposal workflow."""

    INTAKE = "intake"
    RESEARCH = "research"
    WRITING = "writing"
    REVIEW = "review"
    COMPLETED = "completed"


class WorkflowStatus(StrEnum):
    """Execution status of a proposal workflow."""

    PENDING = "pending"
    RUNNING = "running"
    AWAITING_INPUT = "awaiting_input"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskType(StrEnum):
    """Agent task categories."""

    INTAKE = "intake"
    RESEARCH = "research"
    WRITING = "writing"
    REVIEW = "review"


class TaskStatus(StrEnum):
    """Execution status of a workflow task."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AgentExecutionStatus(StrEnum):
    """Execution status of one agent invocation attempt."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
