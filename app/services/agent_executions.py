"""Agent execution persistence services (no agent logic lives here)."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.db.models.agent_execution import AgentExecution
from app.domain.enums import AgentExecutionStatus
from app.domain.errors import EntityNotFoundError, InvalidStateTransitionError
from app.domain.workflow import validate_agent_execution_transition
from app.repositories.agent_executions import AgentExecutionRepository
from app.repositories.tasks import TaskRepository


class AgentExecutionService:
    """Record agent invocation attempts and outcomes."""

    def __init__(self, session: Session) -> None:
        self._executions = AgentExecutionRepository(session)
        self._tasks = TaskRepository(session)

    def get_execution(self, execution_id: str) -> AgentExecution:
        execution = self._executions.get(execution_id)
        if execution is None:
            raise EntityNotFoundError(f"Agent execution '{execution_id}' does not exist")
        return execution

    def start_execution(
        self,
        *,
        task_id: str,
        agent_name: str,
        provider: str,
        model_name: str,
        input_payload: dict[str, Any] | None = None,
    ) -> AgentExecution:
        task = self._tasks.get(task_id)
        if task is None:
            raise EntityNotFoundError(f"Task '{task_id}' does not exist")
        if not agent_name.strip() or not provider.strip() or not model_name.strip():
            raise InvalidStateTransitionError(
                "agent_name, provider, and model_name must not be blank"
            )

        execution = self._executions.create(
            task_id=task.id,
            agent_name=agent_name.strip(),
            provider=provider.strip(),
            model_name=model_name.strip(),
            attempt=self._executions.next_attempt(task.id),
            input_payload=input_payload,
            status=AgentExecutionStatus.RUNNING,
        )
        return self._executions.mark_started(execution, datetime.now(UTC))

    def complete_execution(
        self,
        execution_id: str,
        *,
        output_payload: dict[str, Any] | None = None,
        token_usage: dict[str, Any] | None = None,
        latency_ms: int | None = None,
    ) -> AgentExecution:
        execution = self.get_execution(execution_id)
        if execution.status != AgentExecutionStatus.RUNNING:
            raise InvalidStateTransitionError(
                f"Only running executions can complete; found '{execution.status}'"
            )
        validate_agent_execution_transition(execution.status, AgentExecutionStatus.COMPLETED)
        if latency_ms is not None and latency_ms < 0:
            raise InvalidStateTransitionError("latency_ms must be non-negative")
        return self._executions.mark_completed(
            execution,
            completed_at=datetime.now(UTC),
            output_payload=output_payload,
            token_usage=token_usage,
            latency_ms=latency_ms,
        )

    def fail_execution(self, execution_id: str, *, error_message: str) -> AgentExecution:
        execution = self.get_execution(execution_id)
        if execution.status != AgentExecutionStatus.RUNNING:
            raise InvalidStateTransitionError(
                f"Only running executions can fail; found '{execution.status}'"
            )
        validate_agent_execution_transition(execution.status, AgentExecutionStatus.FAILED)
        if not error_message.strip():
            raise InvalidStateTransitionError("Failed executions require an error_message")
        return self._executions.mark_failed(
            execution,
            completed_at=datetime.now(UTC),
            error_message=error_message,
        )

    def cancel_execution(self, execution_id: str) -> AgentExecution:
        execution = self.get_execution(execution_id)
        if execution.status != AgentExecutionStatus.RUNNING:
            raise InvalidStateTransitionError(
                f"Only running executions can be cancelled; found '{execution.status}'"
            )
        validate_agent_execution_transition(execution.status, AgentExecutionStatus.CANCELLED)
        return self._executions.mark_cancelled(
            execution,
            completed_at=datetime.now(UTC),
        )
