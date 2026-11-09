"""Service-layer validation and state-update tests."""

from uuid import UUID, uuid4

import pytest
from sqlalchemy.orm import Session

from app.db.database import Database
from app.db.models.document import DocumentKind
from app.domain.enums import DocumentRole, TaskStatus, TaskType, WorkflowStage, WorkflowStatus
from app.domain.errors import (
    InvalidStateError,
    InvalidStateTransitionError,
    ReferenceConsistencyError,
    StateVersionConflictError,
)
from app.repositories.documents import DocumentRepository
from app.repositories.users import UserRepository
from app.schemas.workflow import WorkflowStateUpdate
from app.services.agent_executions import AgentExecutionService
from app.services.documents import DocumentService
from app.services.tasks import TaskService
from app.services.workflows import WorkflowService

pytestmark = pytest.mark.unit


def _document(
    session: Session,
    *,
    suffix: str,
    owner_id: str | None = None,
    kind: DocumentKind = DocumentKind.REFERENCE,
) -> str:
    document = DocumentRepository(session).create(
        document_id=str(uuid4()),
        owner_id=owner_id,
        kind=kind,
        source_name=f"{suffix}.txt",
        source_type="txt",
        content_hash=f"hash-{suffix}",
        byte_size=10,
        embedding_provider="test",
        embedding_model="test-model",
        document_metadata={},
    )
    return document.id


def _workflow_setup(session: Session) -> tuple[str, str, str, str]:
    user = UserRepository(session).create(
        slack_user_id="U-service",
        display_name="Service User",
    )
    transcript = _document(session, suffix="transcript", owner_id=user.id)
    reference = _document(session, suffix="reference", owner_id=user.id)
    output = _document(
        session, suffix="output", owner_id=user.id, kind=DocumentKind.GENERATED_PROPOSAL
    )
    workflow = WorkflowService(session).create_workflow(
        user_id=user.id,
        input_document_id=transcript,
        reference_document_ids=[reference],
    )
    DocumentService(session).attach_to_workflow(
        workflow_id=workflow.id,
        document_id=output,
        role=DocumentRole.OUTPUT,
    )
    return user.id, transcript, output, workflow.id


def test_workflow_state_progresses_with_versioned_updates(database: Database) -> None:
    with database.session() as session:
        _, transcript, output, workflow_id = _workflow_setup(session)
        service = WorkflowService(session)

        workflow = service.update_state(
            workflow_id,
            WorkflowStateUpdate(
                expected_version=1,
                stage=WorkflowStage.RESEARCH,
                status=WorkflowStatus.RUNNING,
            ),
        )
        session.commit()
        assert workflow.state_version == 2

        service.update_state(
            workflow_id,
            WorkflowStateUpdate(expected_version=2, stage=WorkflowStage.WRITING),
        )
        service.update_state(
            workflow_id,
            WorkflowStateUpdate(expected_version=3, stage=WorkflowStage.REVIEW),
        )
        workflow = service.update_state(
            workflow_id,
            WorkflowStateUpdate(
                expected_version=4,
                stage=WorkflowStage.COMPLETED,
                status=WorkflowStatus.COMPLETED,
                output_document_id=UUID(output),
            ),
        )
        session.commit()

        snapshot = service.get_snapshot(workflow_id)
        assert workflow.state_version == 5
        assert workflow.status == WorkflowStatus.COMPLETED
        assert workflow.output_document_id == output
        assert workflow.completed_at is not None
        assert snapshot.state.input_document_id == UUID(transcript)
        assert snapshot.state.output_document_id == UUID(output)
        assert snapshot.state_version == 5


def test_stale_state_update_and_invalid_transition_are_rejected(database: Database) -> None:
    with database.session() as session:
        _, _, _, workflow_id = _workflow_setup(session)
        service = WorkflowService(session)
        service.update_state(
            workflow_id,
            WorkflowStateUpdate(
                expected_version=1,
                stage=WorkflowStage.RESEARCH,
                status=WorkflowStatus.RUNNING,
            ),
        )

        with pytest.raises(StateVersionConflictError):
            service.update_state(
                workflow_id,
                WorkflowStateUpdate(expected_version=1, stage=WorkflowStage.WRITING),
            )

        with pytest.raises(InvalidStateTransitionError):
            service.update_state(
                workflow_id,
                WorkflowStateUpdate(expected_version=2, stage=WorkflowStage.INTAKE),
            )


def test_unlinked_document_reference_is_rejected(database: Database) -> None:
    with database.session() as session:
        _, _, _, workflow_id = _workflow_setup(session)
        unlinked = _document(session, suffix="unlinked")
        service = WorkflowService(session)

        with pytest.raises(ReferenceConsistencyError, match="not associated"):
            service.update_state(
                workflow_id,
                WorkflowStateUpdate(
                    expected_version=1,
                    draft_document_id=UUID(unlinked),
                ),
            )

        assert service.get_workflow(workflow_id).state_version == 1


def test_completion_without_output_is_rejected_by_state_validation(database: Database) -> None:
    with database.session() as session:
        _, _, _, workflow_id = _workflow_setup(session)
        service = WorkflowService(session)

        with pytest.raises(InvalidStateError):
            service.update_state(
                workflow_id,
                WorkflowStateUpdate(
                    expected_version=1,
                    stage=WorkflowStage.COMPLETED,
                    status=WorkflowStatus.COMPLETED,
                ),
            )


def test_task_and_agent_execution_services_enforce_references_and_status(
    database: Database,
) -> None:
    with database.session() as session:
        user_id, transcript, _, workflow_id = _workflow_setup(session)
        other_input = _document(session, suffix="other", owner_id=user_id)
        other_workflow = WorkflowService(session).create_workflow(
            user_id=user_id,
            input_document_id=other_input,
        )

        tasks = TaskService(session)
        with pytest.raises(ReferenceConsistencyError, match="not associated"):
            tasks.create_task(
                workflow_id=workflow_id,
                task_type=TaskType.RESEARCH,
                input_document_id=other_input,
            )

        task = tasks.create_task(
            workflow_id=workflow_id,
            task_type=TaskType.INTAKE,
            input_document_id=transcript,
        )
        assert task.sequence == 1
        second_task = tasks.create_task(
            workflow_id=workflow_id,
            task_type=TaskType.RESEARCH,
        )
        assert second_task.sequence == 2

        with pytest.raises(ReferenceConsistencyError, match="error_message"):
            tasks.update_status(task.id, TaskStatus.FAILED)

        running = tasks.update_status(task.id, TaskStatus.RUNNING)
        assert running.started_at is not None
        completed = tasks.update_status(
            task.id,
            TaskStatus.COMPLETED,
            result={"requirements": ["inventory visibility"]},
        )
        assert completed.completed_at is not None
        assert completed.result["requirements"] == ["inventory visibility"]

        with pytest.raises(InvalidStateTransitionError):
            tasks.update_status(task.id, TaskStatus.RUNNING)

        executions = AgentExecutionService(session)
        first = executions.start_execution(
            task_id=task.id,
            agent_name="intake",
            provider="gemini",
            model_name="test-model",
            input_payload={"source": "transcript"},
        )
        assert first.attempt == 1
        finished = executions.complete_execution(
            first.id,
            output_payload={"industry": "retail"},
            token_usage={"prompt_tokens": 10, "completion_tokens": 4},
            latency_ms=250,
        )
        assert finished.status.value == "completed"
        assert finished.output_payload["industry"] == "retail"

        with pytest.raises(InvalidStateTransitionError):
            executions.complete_execution(first.id)

        second = executions.start_execution(
            task_id=task.id,
            agent_name="intake",
            provider="gemini",
            model_name="test-model",
        )
        assert second.attempt == 2
        failed = executions.fail_execution(second.id, error_message="rate limited")
        assert failed.error_message == "rate limited"

        assert other_workflow.id != workflow_id
