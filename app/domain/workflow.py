"""State transition rules for workflows, tasks, and agent executions."""

from collections.abc import Mapping

from app.domain.enums import AgentExecutionStatus, TaskStatus, WorkflowStage, WorkflowStatus
from app.domain.errors import InvalidStateTransitionError

WORKFLOW_STAGE_TRANSITIONS: Mapping[WorkflowStage, frozenset[WorkflowStage]] = {
    WorkflowStage.INTAKE: frozenset({WorkflowStage.RESEARCH}),
    WorkflowStage.RESEARCH: frozenset({WorkflowStage.WRITING}),
    WorkflowStage.WRITING: frozenset({WorkflowStage.REVIEW}),
    WorkflowStage.REVIEW: frozenset({WorkflowStage.WRITING, WorkflowStage.COMPLETED}),
    WorkflowStage.COMPLETED: frozenset(),
}

WORKFLOW_STATUS_TRANSITIONS: Mapping[WorkflowStatus, frozenset[WorkflowStatus]] = {
    WorkflowStatus.PENDING: frozenset(
        {
            WorkflowStatus.RUNNING,
            WorkflowStatus.AWAITING_INPUT,
            WorkflowStatus.FAILED,
            WorkflowStatus.CANCELLED,
        }
    ),
    WorkflowStatus.RUNNING: frozenset(
        {
            WorkflowStatus.AWAITING_INPUT,
            WorkflowStatus.COMPLETED,
            WorkflowStatus.FAILED,
            WorkflowStatus.CANCELLED,
        }
    ),
    WorkflowStatus.AWAITING_INPUT: frozenset(
        {WorkflowStatus.RUNNING, WorkflowStatus.FAILED, WorkflowStatus.CANCELLED}
    ),
    WorkflowStatus.COMPLETED: frozenset(),
    WorkflowStatus.FAILED: frozenset(),
    WorkflowStatus.CANCELLED: frozenset(),
}

TASK_STATUS_TRANSITIONS: Mapping[TaskStatus, frozenset[TaskStatus]] = {
    TaskStatus.PENDING: frozenset({TaskStatus.RUNNING, TaskStatus.FAILED, TaskStatus.CANCELLED}),
    TaskStatus.RUNNING: frozenset({TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED}),
    TaskStatus.COMPLETED: frozenset(),
    TaskStatus.FAILED: frozenset(),
    TaskStatus.CANCELLED: frozenset(),
}

AGENT_EXECUTION_STATUS_TRANSITIONS: Mapping[
    AgentExecutionStatus, frozenset[AgentExecutionStatus]
] = {
    AgentExecutionStatus.PENDING: frozenset(
        {AgentExecutionStatus.RUNNING, AgentExecutionStatus.FAILED, AgentExecutionStatus.CANCELLED}
    ),
    AgentExecutionStatus.RUNNING: frozenset(
        {
            AgentExecutionStatus.COMPLETED,
            AgentExecutionStatus.FAILED,
            AgentExecutionStatus.CANCELLED,
        }
    ),
    AgentExecutionStatus.COMPLETED: frozenset(),
    AgentExecutionStatus.FAILED: frozenset(),
    AgentExecutionStatus.CANCELLED: frozenset(),
}


def validate_workflow_transition(
    *,
    current_stage: WorkflowStage,
    next_stage: WorkflowStage,
    current_status: WorkflowStatus,
    next_status: WorkflowStatus,
) -> None:
    """Validate workflow stage and status changes.

    No-op transitions are always permitted so callers can update unrelated
    state fields without manufacturing a stage change.
    """

    if next_stage != current_stage and next_stage not in WORKFLOW_STAGE_TRANSITIONS[current_stage]:
        raise InvalidStateTransitionError(
            f"Workflow stage cannot transition from '{current_stage}' to '{next_stage}'"
        )
    if (
        next_status != current_status
        and next_status not in WORKFLOW_STATUS_TRANSITIONS[current_status]
    ):
        raise InvalidStateTransitionError(
            f"Workflow status cannot transition from '{current_status}' to '{next_status}'"
        )


def validate_task_transition(current: TaskStatus, next: TaskStatus) -> None:
    """Validate a task status change."""

    if next != current and next not in TASK_STATUS_TRANSITIONS[current]:
        raise InvalidStateTransitionError(
            f"Task status cannot transition from '{current}' to '{next}'"
        )


def validate_agent_execution_transition(
    current: AgentExecutionStatus, next: AgentExecutionStatus
) -> None:
    """Validate an agent-execution status change."""

    if next != current and next not in AGENT_EXECUTION_STATUS_TRANSITIONS[current]:
        raise InvalidStateTransitionError(
            f"Agent execution status cannot transition from '{current}' to '{next}'"
        )
