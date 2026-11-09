"""Structured workflow application-state schemas and update validation."""

from datetime import datetime
from typing import Any, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domain.enums import WorkflowStage, WorkflowStatus
from app.schemas.intake import IntakeResult
from app.schemas.planning import PlanningResult
from app.schemas.research import ResearchResult
from app.schemas.writing import WritingResult


class WorkflowState(BaseModel):
    """Validated state persisted on a workflow.

    The JSON document is the agent-facing state contract. Workflow columns
    mirror the stage, status, input document, output document, and error so
    they can be queried efficiently without inspecting JSON.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    stage: WorkflowStage = WorkflowStage.INTAKE
    status: WorkflowStatus = WorkflowStatus.PENDING
    input_document_id: UUID | None = None
    reference_document_ids: list[UUID] = Field(default_factory=list)
    active_task_id: UUID | None = None
    completed_task_ids: list[UUID] = Field(default_factory=list)
    draft_document_id: UUID | None = None
    output_document_id: UUID | None = None
    intake: IntakeResult | None = None
    extracted_requirements: dict[str, Any] = Field(default_factory=dict)
    research: ResearchResult | None = None
    outline: PlanningResult | None = None
    draft: WritingResult | None = None
    research_notes: str | None = Field(default=None, max_length=20_000)
    revision_count: int = Field(default=0, ge=0)
    last_agent: str | None = Field(default=None, max_length=100)
    last_error: str | None = Field(default=None, max_length=2_000)

    @field_validator("reference_document_ids", "completed_task_ids")
    @classmethod
    def ids_must_be_unique(cls, value: list[UUID]) -> list[UUID]:
        if len(set(value)) != len(value):
            raise ValueError("ID lists must not contain duplicates")
        return value

    @model_validator(mode="after")
    def validate_terminal_state(self) -> Self:
        if self.stage == WorkflowStage.COMPLETED and self.status != WorkflowStatus.COMPLETED:
            raise ValueError("A completed stage requires completed status")
        if self.status == WorkflowStatus.COMPLETED:
            if self.stage != WorkflowStage.COMPLETED:
                raise ValueError("Completed status requires a completed stage")
            if self.output_document_id is None:
                raise ValueError("Completed workflows require an output document")
        if self.status == WorkflowStatus.FAILED and not (self.last_error or "").strip():
            raise ValueError("Failed workflows require a last_error message")
        if self.active_task_id is not None and self.active_task_id in self.completed_task_ids:
            raise ValueError("active_task_id cannot already be completed")
        if self.outline is not None and self.research is None:
            raise ValueError("An outline requires research results")
        if self.draft is not None and self.outline is None:
            raise ValueError("A draft requires an approved outline")
        return self


class WorkflowStateUpdate(BaseModel):
    """Partial update applied to a workflow state with optimistic locking."""

    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    stage: WorkflowStage | None = None
    status: WorkflowStatus | None = None
    input_document_id: UUID | None = None
    reference_document_ids: list[UUID] | None = None
    active_task_id: UUID | None = None
    completed_task_ids: list[UUID] | None = None
    draft_document_id: UUID | None = None
    output_document_id: UUID | None = None
    intake: IntakeResult | None = None
    extracted_requirements: dict[str, Any] | None = None
    research: ResearchResult | None = None
    outline: PlanningResult | None = None
    draft: WritingResult | None = None
    research_notes: str | None = Field(default=None, max_length=20_000)
    revision_count: int | None = Field(default=None, ge=0)
    last_agent: str | None = Field(default=None, max_length=100)
    last_error: str | None = Field(default=None, max_length=2_000)

    @model_validator(mode="after")
    def require_at_least_one_change(self) -> Self:
        changed = self.model_fields_set - {"expected_version"}
        if not changed:
            raise ValueError("State update must contain at least one field to change")
        return self

    def apply_to(self, current: WorkflowState) -> WorkflowState:
        """Merge explicitly supplied fields into an existing state and revalidate."""

        updates = self.model_dump(exclude_unset=True)
        updates.pop("expected_version")
        merged = current.model_dump()
        merged.update(updates)
        return WorkflowState.model_validate(merged)


class WorkflowStateSnapshot(BaseModel):
    """Read-only view of a workflow row and its validated state payload."""

    model_config = ConfigDict(from_attributes=True)

    workflow_id: UUID
    user_id: UUID
    state_version: int
    stage: WorkflowStage
    status: WorkflowStatus
    state: WorkflowState
    created_at: datetime
    updated_at: datetime
