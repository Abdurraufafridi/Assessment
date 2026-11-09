"""Repository for workflow state records."""

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.workflow import Workflow
from app.domain.enums import WorkflowStage, WorkflowStatus


class WorkflowRepository:
    """Data-access operations for :class:`Workflow`."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, workflow_id: str) -> Workflow | None:
        return self._session.get(Workflow, workflow_id)

    def get_for_user(self, workflow_id: str, user_id: str) -> Workflow | None:
        statement = select(Workflow).where(
            Workflow.id == workflow_id,
            Workflow.user_id == user_id,
        )
        return self._session.execute(statement).scalar_one_or_none()

    def list_by_user(self, user_id: str, *, limit: int = 100, offset: int = 0) -> list[Workflow]:
        statement = (
            select(Workflow)
            .where(Workflow.user_id == user_id)
            .order_by(Workflow.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(self._session.execute(statement).scalars())

    def create(
        self,
        *,
        user_id: str,
        state: dict[str, Any],
        stage: WorkflowStage = WorkflowStage.INTAKE,
        status: WorkflowStatus = WorkflowStatus.PENDING,
        input_document_id: str | None = None,
        output_document_id: str | None = None,
        state_version: int = 1,
    ) -> Workflow:
        workflow = Workflow(
            user_id=user_id,
            state=state,
            stage=stage,
            status=status,
            input_document_id=input_document_id,
            output_document_id=output_document_id,
            state_version=state_version,
        )
        self._session.add(workflow)
        self._session.flush()
        return workflow

    def update_state(
        self,
        workflow: Workflow,
        *,
        state: dict[str, Any],
        state_version: int,
        stage: WorkflowStage,
        status: WorkflowStatus,
        input_document_id: str | None,
        output_document_id: str | None,
        last_error: str | None,
        completed_at: datetime | None,
    ) -> Workflow:
        workflow.state = state
        workflow.state_version = state_version
        workflow.stage = stage
        workflow.status = status
        workflow.input_document_id = input_document_id
        workflow.output_document_id = output_document_id
        workflow.last_error = last_error
        workflow.completed_at = completed_at
        self._session.flush()
        return workflow

    def delete(self, workflow: Workflow) -> None:
        self._session.delete(workflow)
