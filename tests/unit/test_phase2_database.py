"""Phase 2 ORM, repository, relationship, and constraint tests."""

from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.database import Database
from app.db.models.document import Document, DocumentKind
from app.db.models.task import Task
from app.db.models.user import User
from app.domain.enums import DocumentRole, TaskType
from app.repositories.agent_executions import AgentExecutionRepository
from app.repositories.documents import DocumentRepository
from app.repositories.tasks import TaskRepository
from app.repositories.users import UserRepository
from app.repositories.workflow_documents import WorkflowDocumentRepository
from app.repositories.workflows import WorkflowRepository
from app.services.agent_executions import AgentExecutionService
from app.services.tasks import TaskService
from app.services.users import UserService
from app.services.workflows import WorkflowService

pytestmark = pytest.mark.unit


def _create_user(session: Session, slack_user_id: str = "U123") -> User:
    return UserRepository(session).create(
        slack_user_id=slack_user_id,
        display_name="Test User",
        email=f"{slack_user_id.lower()}@example.com",
    )


def _create_document(
    session: Session,
    *,
    suffix: str,
    owner_id: str | None = None,
    kind: DocumentKind = DocumentKind.REFERENCE,
) -> Document:
    return DocumentRepository(session).create(
        document_id=str(uuid4()),
        owner_id=owner_id,
        kind=kind,
        source_name=f"document-{suffix}.txt",
        source_type="txt",
        content_hash=f"hash-{suffix}",
        byte_size=100,
        embedding_provider="test",
        embedding_model="test-model",
        document_metadata={"suffix": suffix},
    )


def test_user_crud(database: Database) -> None:
    with database.session() as session:
        users = UserRepository(session)
        user = users.create(
            slack_user_id="U123",
            display_name="Ada",
            email="ADA@EXAMPLE.COM",
        )
        session.commit()
        user_id = user.id

    with database.session() as session:
        users = UserRepository(session)
        stored = users.get(user_id)
        assert stored is not None
        assert stored.display_name == "Ada"
        assert users.get_by_slack_user_id("U123") is stored

        users.update(stored, display_name="Ada Lovelace", is_active=False)
        session.commit()

    with database.session() as session:
        users = UserRepository(session)
        stored = users.get(user_id)
        assert stored is not None
        assert stored.display_name == "Ada Lovelace"
        assert stored.is_active is False
        assert [item.id for item in users.list()] == [user_id]

        users.delete(stored)
        session.commit()

    with database.session() as session:
        assert UserRepository(session).get(user_id) is None


def test_workflow_task_document_and_execution_relationships(database: Database) -> None:
    with database.session() as session:
        user = _create_user(session)
        transcript = _create_document(
            session, suffix="transcript", owner_id=user.id, kind=DocumentKind.CLIENT_TRANSCRIPT
        )
        reference = _create_document(
            session, suffix="reference", owner_id=user.id, kind=DocumentKind.PAST_PROPOSAL
        )
        workflow = WorkflowService(session).create_workflow(
            user_id=user.id,
            input_document_id=transcript.id,
            reference_document_ids=[reference.id],
        )
        task = TaskService(session).create_task(
            workflow_id=workflow.id,
            task_type=TaskType.INTAKE,
            input_document_id=transcript.id,
        )
        execution = AgentExecutionService(session).start_execution(
            task_id=task.id,
            agent_name="intake",
            provider="gemini",
            model_name="test-model",
            input_payload={"document_id": transcript.id},
        )
        session.commit()
        ids = {
            "user": user.id,
            "transcript": transcript.id,
            "reference": reference.id,
            "workflow": workflow.id,
            "task": task.id,
            "execution": execution.id,
        }

    with database.session() as session:
        user = UserRepository(session).get(ids["user"])
        workflow = WorkflowRepository(session).get(ids["workflow"])
        task = TaskRepository(session).get(ids["task"])
        execution = AgentExecutionRepository(session).get(ids["execution"])
        document = DocumentRepository(session).get(ids["transcript"])

        assert user is not None
        assert [item.id for item in user.workflows] == [ids["workflow"]]
        assert {item.id for item in user.documents} == {
            ids["transcript"],
            ids["reference"],
        }

        assert workflow is not None
        assert workflow.user.id == ids["user"]
        assert workflow.input_document is not None
        assert workflow.input_document.id == ids["transcript"]
        assert [item.id for item in workflow.tasks] == [ids["task"]]
        assert {link.document_id for link in workflow.document_links} == {
            ids["transcript"],
            ids["reference"],
        }
        assert {link.role for link in workflow.document_links} == {
            DocumentRole.INPUT,
            DocumentRole.REFERENCE,
        }

        assert task is not None
        assert task.workflow.id == ids["workflow"]
        assert task.input_document is not None
        assert task.input_document.id == ids["transcript"]
        assert [item.id for item in task.executions] == [ids["execution"]]

        assert execution is not None
        assert execution.task.id == ids["task"]
        assert execution.input_payload["document_id"] == ids["transcript"]

        assert document is not None
        assert document.owner is not None
        assert document.owner.id == ids["user"]


def test_foreign_keys_and_check_constraints_are_enforced(database: Database) -> None:
    with database.session() as session:
        foreign_keys = session.connection().exec_driver_sql("PRAGMA foreign_keys").scalar_one()
    assert foreign_keys == 1

    with pytest.raises(IntegrityError), database.session() as session:
        session.add(Task(workflow_id="missing-workflow", task_type=TaskType.INTAKE, sequence=1))
        session.commit()

    with pytest.raises(IntegrityError), database.session() as session:
        session.add(
            Document(
                source_name="bad.txt",
                source_type="txt",
                content_hash="bad-hash",
                byte_size=-1,
                embedding_provider="test",
                embedding_model="test-model",
            )
        )
        session.commit()


def test_task_sequence_is_unique_per_workflow(database: Database) -> None:
    with database.session() as session:
        user = _create_user(session)
        workflow = WorkflowRepository(session).create(
            user_id=user.id,
            state={},
        )
        tasks = TaskRepository(session)
        tasks.create(
            workflow_id=workflow.id,
            task_type=TaskType.INTAKE,
            sequence=1,
        )
        session.commit()

    with pytest.raises(IntegrityError), database.session() as session:
        TaskRepository(session).create(
            workflow_id=workflow.id,
            task_type=TaskType.RESEARCH,
            sequence=1,
        )
        session.commit()


def test_workflow_delete_cascades_tasks_links_and_executions(database: Database) -> None:
    with database.session() as session:
        user = _create_user(session)
        document = _create_document(session, suffix="cascade", owner_id=user.id)
        workflow = WorkflowService(session).create_workflow(
            user_id=user.id,
            input_document_id=document.id,
        )
        task = TaskService(session).create_task(
            workflow_id=workflow.id,
            task_type=TaskType.INTAKE,
            input_document_id=document.id,
        )
        AgentExecutionService(session).start_execution(
            task_id=task.id,
            agent_name="intake",
            provider="gemini",
            model_name="test-model",
        )
        session.commit()
        workflow_id = workflow.id

    with database.session() as session:
        workflow = WorkflowRepository(session).get(workflow_id)
        assert workflow is not None
        WorkflowRepository(session).delete(workflow)
        session.commit()

    with database.session() as session:
        assert WorkflowRepository(session).get(workflow_id) is None
        assert TaskRepository(session).list_by_workflow(workflow_id) == []
        assert WorkflowDocumentRepository(session).list_by_workflow(workflow_id) == []


def test_user_service_get_or_create_normalises_input(database: Database) -> None:
    with database.session() as session:
        service = UserService(session)
        user = service.get_or_create(
            slack_user_id=" U999 ",
            display_name=" Grace ",
            email="GRACE@EXAMPLE.COM",
        )
        session.commit()

        again = service.get_or_create(
            slack_user_id="U999",
            display_name="Grace Hopper",
            email="grace@example.com",
        )
        session.commit()

        assert again.id == user.id
        assert again.display_name == "Grace Hopper"
        assert again.email == "grace@example.com"


def test_migrations_and_create_all_share_metadata_shape(tmp_path: Path) -> None:
    """Sanity-check that a fresh create_all database can be queried by repositories."""

    database = Database(f"sqlite:///{tmp_path / 'shape.db'}")
    database.create_all()
    try:
        with database.session() as session:
            user = _create_user(session, "U-shape")
            document = _create_document(session, suffix="shape", owner_id=user.id)
            session.commit()

            assert DocumentRepository(session).get(document.id) is not None
    finally:
        database.dispose()
