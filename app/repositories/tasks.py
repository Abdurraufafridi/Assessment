"""Repository for workflow task records."""

from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models.task import Task
from app.domain.enums import TaskStatus, TaskType


class TaskRepository:
    """Data-access operations for :class:`Task`."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, task_id: str) -> Task | None:
        return self._session.get(Task, task_id)

    def list_by_workflow(self, workflow_id: str) -> list[Task]:
        statement = select(Task).where(Task.workflow_id == workflow_id).order_by(Task.sequence)
        return list(self._session.execute(statement).scalars())

    def next_sequence(self, workflow_id: str) -> int:
        statement = select(func.coalesce(func.max(Task.sequence), 0)).where(
            Task.workflow_id == workflow_id
        )
        return int(self._session.execute(statement).scalar_one()) + 1

    def create(
        self,
        *,
        workflow_id: str,
        task_type: TaskType,
        sequence: int,
        input_document_id: str | None = None,
        output_document_id: str | None = None,
        payload: dict[str, Any] | None = None,
        status: TaskStatus = TaskStatus.PENDING,
    ) -> Task:
        task = Task(
            workflow_id=workflow_id,
            task_type=task_type,
            sequence=sequence,
            input_document_id=input_document_id,
            output_document_id=output_document_id,
            payload=payload or {},
            status=status,
        )
        self._session.add(task)
        self._session.flush()
        return task

    def link_documents(
        self,
        task: Task,
        *,
        input_document_id: str | None = None,
        output_document_id: str | None = None,
    ) -> Task:
        if input_document_id is not None:
            task.input_document_id = input_document_id
        if output_document_id is not None:
            task.output_document_id = output_document_id
        self._session.flush()
        return task

    def mark_started(self, task: Task, started_at: datetime) -> Task:
        task.status = TaskStatus.RUNNING
        task.started_at = started_at
        task.error_message = None
        self._session.flush()
        return task

    def mark_completed(
        self,
        task: Task,
        *,
        completed_at: datetime,
        result: dict[str, Any] | None = None,
        output_document_id: str | None = None,
    ) -> Task:
        task.status = TaskStatus.COMPLETED
        task.completed_at = completed_at
        task.error_message = None
        if result is not None:
            task.result = result
        if output_document_id is not None:
            task.output_document_id = output_document_id
        self._session.flush()
        return task

    def mark_failed(self, task: Task, *, completed_at: datetime, error_message: str) -> Task:
        task.status = TaskStatus.FAILED
        task.completed_at = completed_at
        task.error_message = error_message[:2000]
        self._session.flush()
        return task

    def mark_cancelled(self, task: Task, *, completed_at: datetime) -> Task:
        task.status = TaskStatus.CANCELLED
        task.completed_at = completed_at
        self._session.flush()
        return task

    def delete(self, task: Task) -> None:
        self._session.delete(task)
