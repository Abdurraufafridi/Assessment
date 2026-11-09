"""Workflow application services and state transitions."""

from datetime import UTC, datetime
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.db.models.workflow import Workflow
from app.domain.enums import DocumentRole, WorkflowStatus
from app.domain.errors import (
    EntityNotFoundError,
    InvalidStateError,
    ReferenceConsistencyError,
    StateVersionConflictError,
)
from app.domain.workflow import validate_workflow_transition
from app.repositories.tasks import TaskRepository
from app.repositories.users import UserRepository
from app.repositories.workflow_documents import WorkflowDocumentRepository
from app.repositories.workflows import WorkflowRepository
from app.schemas.workflow import WorkflowState, WorkflowStateSnapshot, WorkflowStateUpdate
from app.services.documents import DocumentService


class WorkflowService:
    """Create workflows and apply validated, versioned state updates."""

    def __init__(self, session: Session) -> None:
        self._session = session
        self._workflows = WorkflowRepository(session)
        self._users = UserRepository(session)
        self._tasks = TaskRepository(session)
        self._links = WorkflowDocumentRepository(session)
        self._documents = DocumentService(session)

    def get_workflow(self, workflow_id: str) -> Workflow:
        workflow = self._workflows.get(workflow_id)
        if workflow is None:
            raise EntityNotFoundError(f"Workflow '{workflow_id}' does not exist")
        return workflow

    def create_workflow(
        self,
        *,
        user_id: str,
        input_document_id: str | None = None,
        reference_document_ids: list[str] | None = None,
    ) -> Workflow:
        user = self._users.get(user_id)
        if user is None:
            raise EntityNotFoundError(f"User '{user_id}' does not exist")

        references = list(reference_document_ids or [])
        if len(references) != len(set(references)):
            raise ReferenceConsistencyError("reference_document_ids must not contain duplicates")
        if input_document_id is not None and input_document_id in references:
            raise ReferenceConsistencyError(
                "The input document cannot also be a reference document"
            )
        state = WorkflowState(
            input_document_id=UUID(input_document_id) if input_document_id else None,
            reference_document_ids=[UUID(value) for value in references],
        )
        workflow = self._workflows.create(
            user_id=user.id,
            state=state.model_dump(mode="json"),
            input_document_id=input_document_id,
        )

        if input_document_id is not None:
            self._documents.attach_to_workflow(
                workflow_id=workflow.id,
                document_id=input_document_id,
                role=DocumentRole.INPUT,
            )
        for reference_id in references:
            self._documents.attach_to_workflow(
                workflow_id=workflow.id,
                document_id=reference_id,
                role=DocumentRole.REFERENCE,
            )
        return workflow

    def add_document(
        self,
        *,
        workflow_id: str,
        document_id: str,
        role: DocumentRole = DocumentRole.REFERENCE,
    ) -> None:
        self._documents.attach_to_workflow(
            workflow_id=workflow_id,
            document_id=document_id,
            role=role,
        )

    def get_state(self, workflow_id: str) -> WorkflowState:
        workflow = self.get_workflow(workflow_id)
        return self._parse_state(workflow)

    def get_snapshot(self, workflow_id: str) -> WorkflowStateSnapshot:
        workflow = self.get_workflow(workflow_id)
        return WorkflowStateSnapshot(
            workflow_id=UUID(workflow.id),
            user_id=UUID(workflow.user_id),
            state_version=workflow.state_version,
            stage=workflow.stage,
            status=workflow.status,
            state=self._parse_state(workflow),
            created_at=workflow.created_at,
            updated_at=workflow.updated_at,
        )

    def update_state(self, workflow_id: str, update: WorkflowStateUpdate) -> Workflow:
        workflow = self.get_workflow(workflow_id)
        if update.expected_version != workflow.state_version:
            raise StateVersionConflictError(
                f"Workflow '{workflow_id}' is at version {workflow.state_version}; "
                f"update expected version {update.expected_version}"
            )

        current = self._parse_state(workflow)
        try:
            next_state = update.apply_to(current)
        except ValidationError as exc:
            raise InvalidStateError(f"Invalid workflow state update: {exc}") from exc

        validate_workflow_transition(
            current_stage=current.stage,
            next_stage=next_state.stage,
            current_status=current.status,
            next_status=next_state.status,
        )
        self._validate_references(workflow, next_state)

        terminal = next_state.status in {
            WorkflowStatus.COMPLETED,
            WorkflowStatus.FAILED,
            WorkflowStatus.CANCELLED,
        }
        completed_at = workflow.completed_at or datetime.now(UTC) if terminal else None

        return self._workflows.update_state(
            workflow,
            state=next_state.model_dump(mode="json"),
            state_version=workflow.state_version + 1,
            stage=next_state.stage,
            status=next_state.status,
            input_document_id=(
                str(next_state.input_document_id)
                if next_state.input_document_id is not None
                else None
            ),
            output_document_id=(
                str(next_state.output_document_id)
                if next_state.output_document_id is not None
                else None
            ),
            last_error=next_state.last_error,
            completed_at=completed_at,
        )

    def _parse_state(self, workflow: Workflow) -> WorkflowState:
        try:
            return WorkflowState.model_validate(workflow.state)
        except ValidationError as exc:
            raise InvalidStateError(
                f"Workflow '{workflow.id}' has an invalid persisted state: {exc}"
            ) from exc

    def _validate_references(self, workflow: Workflow, state: WorkflowState) -> None:
        document_ids = {
            value
            for value in (
                state.input_document_id,
                state.draft_document_id,
                state.output_document_id,
                *state.reference_document_ids,
            )
            if value is not None
        }
        for document_id in document_ids:
            if self._links.get(workflow.id, str(document_id)) is None:
                raise ReferenceConsistencyError(
                    f"Document '{document_id}' is not associated with workflow '{workflow.id}'"
                )

        task_ids = {
            value
            for value in (state.active_task_id, *state.completed_task_ids)
            if value is not None
        }
        for task_id in task_ids:
            task = self._tasks.get(str(task_id))
            if task is None or task.workflow_id != workflow.id:
                raise ReferenceConsistencyError(
                    f"Task '{task_id}' does not belong to workflow '{workflow.id}'"
                )
