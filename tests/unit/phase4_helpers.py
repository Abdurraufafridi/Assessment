"""Shared builders for Phase 4 agent tests."""

import json
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from app.domain.enums import WorkflowStage, WorkflowStatus
from app.repositories.users import UserRepository
from app.schemas.intake import IntakeResult
from app.schemas.planning import OutlineSection, PlanningResult, PlanningStatus
from app.schemas.research import (
    ResearchFinding,
    ResearchResult,
    ResearchStatus,
    SourceReference,
)
from app.schemas.workflow import WorkflowStateUpdate
from app.services.workflows import WorkflowService


def make_intake(**overrides: Any) -> IntakeResult:
    payload: dict[str, Any] = {
        "objective": "Create a proposal for Acme's warehouse modernization.",
        "document_type": "proposal",
        "document_subtype": "technical proposal",
        "audience": "Acme operations leadership",
        "required_inputs": ["Discovery transcript"],
        "constraints": ["Maximum 8 pages", "Professional tone"],
        "missing_information": [],
        "clarification_questions": [],
        "status": "ready",
        "confidence": 0.92,
    }
    payload.update(overrides)
    return IntakeResult.model_validate(payload)


def make_source(
    citation_id: str,
    *,
    chunk_id: str | None = None,
    document_id: str | None = None,
    source_name: str | None = None,
    chunk_index: int = 0,
    score: float = 0.9,
    excerpt: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> SourceReference:
    resolved_document_id = document_id or f"doc-{citation_id.lower()}"
    resolved_source_name = source_name or f"{citation_id.lower()}.txt"
    resolved_chunk_id = chunk_id or f"{resolved_document_id}:{chunk_index:04d}"
    values: dict[str, Any] = {
        "document_id": resolved_document_id,
        "source_name": resolved_source_name,
        "source_type": "txt",
        "chunk_index": chunk_index,
        "industry": "logistics",
        "approved_flag": True,
    }
    if metadata:
        values.update(metadata)
    return SourceReference(
        citation_id=citation_id,
        chunk_id=resolved_chunk_id,
        document_id=resolved_document_id,
        source_name=resolved_source_name,
        source_type="txt",
        chunk_index=chunk_index,
        score=score,
        excerpt=excerpt or f"Evidence for {citation_id}.",
        metadata=values,
    )


def make_research(
    *,
    status: ResearchStatus = ResearchStatus.SUFFICIENT,
    sources: list[SourceReference] | None = None,
    findings: list[ResearchFinding] | None = None,
    missing_evidence: list[str] | None = None,
) -> ResearchResult:
    resolved_sources = sources if sources is not None else [make_source("S1"), make_source("S2")]
    resolved_findings = findings
    if resolved_findings is None and status is ResearchStatus.SUFFICIENT:
        resolved_findings = [
            ResearchFinding(
                claim="Acme needs warehouse modernization support.",
                citation_ids=[resolved_sources[0].citation_id],
                confidence=0.9,
            )
        ]
    return ResearchResult(
        status=status,
        findings=resolved_findings or [],
        missing_evidence=missing_evidence or [],
        coverage=0.85 if status is ResearchStatus.SUFFICIENT else 0.2,
        queries=["warehouse modernization"],
        sources=resolved_sources,
    )


def make_outline(
    *,
    status: PlanningStatus = PlanningStatus.READY,
    missing_evidence: list[str] | None = None,
) -> PlanningResult:
    return PlanningResult(
        title="Acme Warehouse Modernization Proposal",
        sections=[
            OutlineSection(
                heading="Client Needs",
                purpose="Summarize the validated client requirements.",
                key_points=["Modernize warehouse operations"],
                citation_ids=["S1"],
                estimated_words=250,
            ),
            OutlineSection(
                heading="Delivery Approach",
                purpose="Explain the evidence-backed delivery approach.",
                key_points=["Phased implementation"],
                citation_ids=["S2"],
                estimated_words=300,
            ),
        ],
        missing_evidence=missing_evidence or [],
        status=status,
    )


def create_workflow(session: Session) -> str:
    user = UserRepository(session).create(
        slack_user_id=f"U-{uuid4().hex[:8]}",
        display_name="Phase 4 User",
    )
    return WorkflowService(session).create_workflow(user_id=user.id).id


def seed_intake(
    session: Session,
    workflow_id: str,
    *,
    intake: IntakeResult | None = None,
) -> int:
    workflow = WorkflowService(session).update_state(
        workflow_id,
        WorkflowStateUpdate(
            expected_version=1,
            stage=WorkflowStage.INTAKE,
            status=WorkflowStatus.RUNNING,
            intake=intake or make_intake(),
            extracted_requirements=(intake or make_intake()).model_dump(mode="json"),
            last_agent="intake",
        ),
    )
    return workflow.state_version


def seed_research(
    session: Session,
    workflow_id: str,
    *,
    intake: IntakeResult | None = None,
    research: ResearchResult | None = None,
) -> int:
    resolved_intake = intake or make_intake()
    resolved_research = research or make_research()
    workflow = WorkflowService(session).update_state(
        workflow_id,
        WorkflowStateUpdate(
            expected_version=1,
            stage=WorkflowStage.RESEARCH,
            status=WorkflowStatus.RUNNING,
            intake=resolved_intake,
            extracted_requirements=resolved_intake.model_dump(mode="json"),
            research=resolved_research,
            research_notes="# Research Notes",
            last_agent="research",
        ),
    )
    return workflow.state_version


def seed_outline(
    session: Session,
    workflow_id: str,
    *,
    intake: IntakeResult | None = None,
    research: ResearchResult | None = None,
    outline: PlanningResult | None = None,
) -> int:
    resolved_intake = intake or make_intake()
    resolved_research = research or make_research()
    resolved_outline = outline or make_outline()
    workflow = WorkflowService(session).update_state(
        workflow_id,
        WorkflowStateUpdate(
            expected_version=1,
            stage=WorkflowStage.RESEARCH,
            status=WorkflowStatus.RUNNING,
            intake=resolved_intake,
            extracted_requirements=resolved_intake.model_dump(mode="json"),
            research=resolved_research,
            outline=resolved_outline,
            research_notes="# Research Notes",
            last_agent="planning",
        ),
    )
    return workflow.state_version


def json_response(payload: dict[str, Any] | list[Any], *, fenced: bool = False) -> str:
    encoded = json.dumps(payload)
    return f"```json\n{encoded}\n```" if fenced else encoded
