"""Workflow task application services."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.db.models.task import Task
from app.domain.enums import TaskStatus, TaskType
from app.domain.errors import EntityNotFoundError, ReferenceConsistencyError
from app.domain.workflow import validate_task_transition
from app.repositories.tasks import TaskRepository
from app.repositories.workflows import WorkflowRepository
from app.services.documents import DocumentService


class TaskService:
    """Create tasks and enforce status/document reference rules."""

    def __init__(self, session: Session) -> None:
        self._tasks = TaskRepository(session)
        self._workflows = WorkflowRepository(session)
        self._documents = DocumentService(session)

    def get_task(self, task_id: str) -> Task:
        task = self._tasks.get(task_id)
        if task is None:
            raise EntityNotFoundError(f"Task '{task_id}' does not exist")
        return task

    def create_task(
        self,
        *,
        workflow_id: str,
        task_type: TaskType,
        sequence: int | None = None,
        input_document_id: str | None = None,
        output_document_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> Task:
        if self._workflows.get(workflow_id) is None:
            raise EntityNotFoundError(f"Workflow '{workflow_id}' does not exist")

        if input_document_id is not None:
            self._documents.require_workflow_document(
                workflow_id=workflow_id, document_id=input_document_id
            )
        if output_document_id is not None:
            self._documents.require_workflow_document(
                workflow_id=workflow_id, document_id=output_document_id
            )

        resolved_sequence = (
            sequence if sequence is not None else self._tasks.next_sequence(workflow_id)
        )
        if resolved_sequence < 1:
            raise ReferenceConsistencyError("Task sequence must be at least 1")
        return self._tasks.create(
            workflow_id=workflow_id,
            task_type=task_type,
            sequence=resolved_sequence,
            input_document_id=input_document_id,
            output_document_id=output_document_id,
            payload=payload,
        )

    def update_status(
        self,
        task_id: str,
        status: TaskStatus,
        *,
        result: dict[str, Any] | None = None,
        error_message: str | None = None,
        output_document_id: str | None = None,
    ) -> Task:
        task = self.get_task(task_id)
        validate_task_transition(task.status, status)

        if output_document_id is not None:
            self._documents.require_workflow_document(
                workflow_id=task.workflow_id, document_id=output_document_id
            )

        if status == task.status:
            return task

        now = datetime.now(UTC)
        if status == TaskStatus.RUNNING:
            return self._tasks.mark_started(task, now)
        if status == TaskStatus.COMPLETED:
            return self._tasks.mark_completed(
                task,
                completed_at=now,
                result=result,
                output_document_id=output_document_id,
            )
        if status == TaskStatus.FAILED:
            if not (error_message or "").strip():
                raise ReferenceConsistencyError("Failed tasks require an error_message")
            return self._tasks.mark_failed(
                task,
                completed_at=now,
                error_message=error_message or "",
            )
        if status == TaskStatus.CANCELLED:
            return self._tasks.mark_cancelled(task, completed_at=now)
        return task

    def link_documents(
        self,
        task_id: str,
        *,
        input_document_id: str | None = None,
        output_document_id: str | None = None,
    ) -> Task:
        task = self.get_task(task_id)
        for document_id in (input_document_id, output_document_id):
            if document_id is not None:
                self._documents.require_workflow_document(
                    workflow_id=task.workflow_id, document_id=document_id
                )
        return self._tasks.link_documents(
            task,
            input_document_id=input_document_id,
            output_document_id=output_document_id,
        )
