"""Document association services."""

from sqlalchemy.orm import Session

from app.db.models.document import Document
from app.db.models.workflow import Workflow
from app.db.models.workflow_document import WorkflowDocument
from app.domain.enums import DocumentRole
from app.domain.errors import EntityNotFoundError, ReferenceConsistencyError
from app.repositories.documents import DocumentRepository
from app.repositories.workflow_documents import WorkflowDocumentRepository
from app.repositories.workflows import WorkflowRepository


class DocumentService:
    """Validate and maintain document references within workflows."""

    def __init__(self, session: Session) -> None:
        self._documents = DocumentRepository(session)
        self._workflows = WorkflowRepository(session)
        self._links = WorkflowDocumentRepository(session)

    def get_document(self, document_id: str) -> Document:
        document = self._documents.get(document_id)
        if document is None:
            raise EntityNotFoundError(f"Document '{document_id}' does not exist")
        return document

    def get_workflow(self, workflow_id: str) -> Workflow:
        workflow = self._workflows.get(workflow_id)
        if workflow is None:
            raise EntityNotFoundError(f"Workflow '{workflow_id}' does not exist")
        return workflow

    def attach_to_workflow(
        self,
        *,
        workflow_id: str,
        document_id: str,
        role: DocumentRole,
    ) -> WorkflowDocument:
        workflow = self.get_workflow(workflow_id)
        document = self.get_document(document_id)
        self._validate_owner(workflow, document)
        return self._links.upsert(
            workflow_id=workflow.id,
            document_id=document.id,
            role=role,
        )

    def require_workflow_document(self, *, workflow_id: str, document_id: str) -> WorkflowDocument:
        link = self._links.get(workflow_id, document_id)
        if link is None:
            raise ReferenceConsistencyError(
                f"Document '{document_id}' is not associated with workflow '{workflow_id}'"
            )
        return link

    def list_workflow_documents(self, workflow_id: str) -> list[WorkflowDocument]:
        self.get_workflow(workflow_id)
        return self._links.list_by_workflow(workflow_id)

    @staticmethod
    def _validate_owner(workflow: Workflow, document: Document) -> None:
        if document.owner_id is not None and document.owner_id != workflow.user_id:
            raise ReferenceConsistencyError(
                f"Document '{document.id}' belongs to a different user than workflow "
                f"'{workflow.id}'"
            )
