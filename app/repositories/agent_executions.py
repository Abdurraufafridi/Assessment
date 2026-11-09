"""Repository for agent execution records."""

from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models.agent_execution import AgentExecution
from app.domain.enums import AgentExecutionStatus


class AgentExecutionRepository:
    """Data-access operations for :class:`AgentExecution`."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, execution_id: str) -> AgentExecution | None:
        return self._session.get(AgentExecution, execution_id)

    def list_by_task(self, task_id: str) -> list[AgentExecution]:
        statement = (
            select(AgentExecution)
            .where(AgentExecution.task_id == task_id)
            .order_by(AgentExecution.attempt)
        )
        return list(self._session.execute(statement).scalars())

    def next_attempt(self, task_id: str) -> int:
        statement = select(func.coalesce(func.max(AgentExecution.attempt), 0)).where(
            AgentExecution.task_id == task_id
        )
        return int(self._session.execute(statement).scalar_one()) + 1

    def create(
        self,
        *,
        task_id: str,
        agent_name: str,
        provider: str,
        model_name: str,
        attempt: int,
        input_payload: dict[str, Any] | None = None,
        status: AgentExecutionStatus = AgentExecutionStatus.PENDING,
    ) -> AgentExecution:
        execution = AgentExecution(
            task_id=task_id,
            agent_name=agent_name,
            provider=provider,
            model_name=model_name,
            attempt=attempt,
            input_payload=input_payload or {},
            status=status,
        )
        self._session.add(execution)
        self._session.flush()
        return execution

    def mark_started(self, execution: AgentExecution, started_at: datetime) -> AgentExecution:
        execution.status = AgentExecutionStatus.RUNNING
        execution.started_at = started_at
        execution.error_message = None
        self._session.flush()
        return execution

    def mark_completed(
        self,
        execution: AgentExecution,
        *,
        completed_at: datetime,
        output_payload: dict[str, Any] | None = None,
        token_usage: dict[str, Any] | None = None,
        latency_ms: int | None = None,
    ) -> AgentExecution:
        execution.status = AgentExecutionStatus.COMPLETED
        execution.completed_at = completed_at
        execution.error_message = None
        if output_payload is not None:
            execution.output_payload = output_payload
        if token_usage is not None:
            execution.token_usage = token_usage
        if latency_ms is not None:
            execution.latency_ms = latency_ms
        self._session.flush()
        return execution

    def mark_failed(
        self,
        execution: AgentExecution,
        *,
        completed_at: datetime,
        error_message: str,
    ) -> AgentExecution:
        execution.status = AgentExecutionStatus.FAILED
        execution.completed_at = completed_at
        execution.error_message = error_message[:2000]
        self._session.flush()
        return execution

    def mark_cancelled(
        self, execution: AgentExecution, *, completed_at: datetime
    ) -> AgentExecution:
        execution.status = AgentExecutionStatus.CANCELLED
        execution.completed_at = completed_at
        self._session.flush()
        return execution

    def delete(self, execution: AgentExecution) -> None:
        self._session.delete(execution)
