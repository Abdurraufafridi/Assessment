"""Workflow state schema and update-validation tests."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.domain.enums import WorkflowStage, WorkflowStatus
from app.schemas.workflow import WorkflowState, WorkflowStateUpdate
from app.schemas.writing import WritingResult, WritingSection
from tests.unit.phase4_helpers import make_outline, make_research, make_source

pytestmark = pytest.mark.unit


def test_default_state_is_valid() -> None:
    state = WorkflowState()

    assert state.stage == WorkflowStage.INTAKE
    assert state.status == WorkflowStatus.PENDING
    assert state.revision_count == 0
    assert state.research is None
    assert state.outline is None
    assert state.draft is None


def test_phase4_state_requires_prerequisite_agents() -> None:
    with pytest.raises(ValidationError, match="outline requires research"):
        WorkflowState(outline=make_outline())

    source = make_source("S1")
    draft = WritingResult(
        title="Draft",
        sections=[
            WritingSection(
                heading="Client Needs",
                content="Supported content [S1].",
                citation_ids=["S1"],
            )
        ],
        sources=[source],
    )
    with pytest.raises(ValidationError, match="draft requires an approved outline"):
        WorkflowState(draft=draft)
    with pytest.raises(ValidationError, match="draft requires an approved outline"):
        WorkflowState(research=make_research(), draft=draft)


def test_completed_state_requires_completed_stage_and_output() -> None:
    with pytest.raises(ValidationError, match="completed stage requires completed status"):
        WorkflowState(stage=WorkflowStage.COMPLETED)

    with pytest.raises(ValidationError, match="Completed status requires a completed stage"):
        WorkflowState(status=WorkflowStatus.COMPLETED, output_document_id=uuid4())

    with pytest.raises(ValidationError, match="require an output document"):
        WorkflowState(
            stage=WorkflowStage.COMPLETED,
            status=WorkflowStatus.COMPLETED,
        )

    state = WorkflowState(
        stage=WorkflowStage.COMPLETED,
        status=WorkflowStatus.COMPLETED,
        output_document_id=uuid4(),
    )
    assert state.status == WorkflowStatus.COMPLETED


def test_failed_state_requires_error_message() -> None:
    with pytest.raises(ValidationError, match="require a last_error"):
        WorkflowState(status=WorkflowStatus.FAILED)

    state = WorkflowState(status=WorkflowStatus.FAILED, last_error="provider unavailable")
    assert state.last_error == "provider unavailable"


def test_duplicate_references_and_active_completed_task_are_rejected() -> None:
    document_id = uuid4()
    task_id = uuid4()

    with pytest.raises(ValidationError, match="duplicates"):
        WorkflowState(reference_document_ids=[document_id, document_id])

    with pytest.raises(ValidationError, match="cannot already be completed"):
        WorkflowState(active_task_id=task_id, completed_task_ids=[task_id])


def test_update_requires_a_change_and_uses_optimistic_version() -> None:
    with pytest.raises(ValidationError, match="at least one field"):
        WorkflowStateUpdate(expected_version=1)

    update = WorkflowStateUpdate(expected_version=1, stage=WorkflowStage.RESEARCH)
    assert update.expected_version == 1


def test_update_applies_explicit_values_including_clearing() -> None:
    document_id = uuid4()
    current = WorkflowState(
        status=WorkflowStatus.RUNNING,
        input_document_id=document_id,
        research_notes="initial notes",
    )
    update = WorkflowStateUpdate(
        expected_version=1,
        stage=WorkflowStage.RESEARCH,
        research_notes=None,
        input_document_id=None,
    )

    updated = update.apply_to(current)

    assert updated.stage == WorkflowStage.RESEARCH
    assert updated.status == WorkflowStatus.RUNNING
    assert updated.input_document_id is None
    assert updated.research_notes is None


def test_state_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="Extra inputs"):
        WorkflowState.model_validate({"unknown": "value"})
