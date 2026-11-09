"""Repository for workflow-document associations."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.workflow_document import WorkflowDocument
from app.domain.enums import DocumentRole


class WorkflowDocumentRepository:
    """Data-access operations for :class:`WorkflowDocument`."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, workflow_id: str, document_id: str) -> WorkflowDocument | None:
        return self._session.get(WorkflowDocument, (workflow_id, document_id))

    def list_by_workflow(self, workflow_id: str) -> list[WorkflowDocument]:
        statement = (
            select(WorkflowDocument)
            .where(WorkflowDocument.workflow_id == workflow_id)
            .order_by(WorkflowDocument.created_at)
        )
        return list(self._session.execute(statement).scalars())

    def upsert(
        self,
        *,
        workflow_id: str,
        document_id: str,
        role: DocumentRole,
    ) -> WorkflowDocument:
        link = self.get(workflow_id, document_id)
        if link is None:
            link = WorkflowDocument(
                workflow_id=workflow_id,
                document_id=document_id,
                role=role,
            )
            self._session.add(link)
        else:
            link.role = role
        self._session.flush()
        return link

    def remove(self, link: WorkflowDocument) -> None:
        self._session.delete(link)
