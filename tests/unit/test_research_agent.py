"""Independent tests for the Phase 4 research agent."""

from collections.abc import Mapping
from typing import Any

import pytest
from sqlalchemy.orm import Session

from app.agents.errors import InvalidResearchOutputError, ResearchRequestError
from app.agents.research import ResearchAgent
from app.db.database import Database
from app.domain.enums import WorkflowStage, WorkflowStatus
from app.ingestion.metadata import MetadataValue
from app.schemas.research import ResearchStatus
from app.schemas.workflow import WorkflowStateUpdate
from app.services.workflows import WorkflowService
from app.vectorstore.base import VectorSearchResult
from tests.unit.phase4_helpers import (
    create_workflow,
    json_response,
    make_intake,
    seed_intake,
)

pytestmark = pytest.mark.unit


class FakeLLM:
    provider_name = "fake"
    model_name = "fake-research"

    def __init__(self, response: str) -> None:
        self.response = response
        self.calls: list[tuple[str, str]] = []

    def generate(self, *, system_prompt: str, user_prompt: str) -> str:
        self.calls.append((system_prompt, user_prompt))
        return self.response


class FakeRetriever:
    def __init__(self, results: list[VectorSearchResult]) -> None:
        self.results = results
        self.calls: list[tuple[str, int]] = []

    def search(
        self,
        query: str,
        *,
        top_k: int = 6,
        where: Mapping[str, MetadataValue] | None = None,
    ) -> list[VectorSearchResult]:
        del where
        self.calls.append((query, top_k))
        return self.results[:top_k]


def _result(
    *,
    chunk_id: str,
    document_id: str,
    source_name: str,
    text: str,
    score: float,
    chunk_index: int,
    metadata: dict[str, Any] | None = None,
) -> VectorSearchResult:
    values: dict[str, MetadataValue] = {
        "document_id": document_id,
        "source_name": source_name,
        "source_type": "txt",
        "chunk_index": chunk_index,
        "industry": "logistics",
        "content_hash": f"hash-{document_id}",
    }
    if metadata:
        for key, value in metadata.items():
            if isinstance(value, (str, int, float, bool)):
                values[key] = value
    return VectorSearchResult(
        id=chunk_id,
        text=text,
        metadata=values,
        distance=1.0 - score,
        score=score,
    )


def _analysis_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "status": "sufficient",
        "findings": [
            {
                "claim": "Acme's warehouse needs real-time inventory visibility.",
                "citation_ids": ["S1"],
                "confidence": 0.9,
            },
            {
                "claim": "The engagement should use a phased delivery approach.",
                "citation_ids": ["S2"],
                "confidence": 0.8,
            },
        ],
        "missing_evidence": [],
        "coverage": 0.85,
    }
    payload.update(overrides)
    return payload


def _retriever() -> FakeRetriever:
    return FakeRetriever(
        [
            _result(
                chunk_id="doc-a:0000",
                document_id="doc-a",
                source_name="proposal_logistics.txt",
                text="Acme requires real-time inventory visibility across three warehouses.",
                score=0.93,
                chunk_index=0,
                metadata={"proposal_type": "past_proposal", "page": 3},
            ),
            _result(
                chunk_id="doc-b:0001",
                document_id="doc-b",
                source_name="client_transcript.txt",
                text="The client requested a phased rollout starting in the first quarter.",
                score=0.81,
                chunk_index=1,
            ),
        ]
    )


def test_research_retrieves_evidence_and_preserves_source_metadata() -> None:
    llm = FakeLLM(json_response(_analysis_payload(), fenced=True))
    retriever = _retriever()
    agent = ResearchAgent(
        llm=llm,
        workflows=WorkflowService(Session()),
        retriever=retriever,
    )

    result = agent.analyze(make_intake())

    assert result.status is ResearchStatus.SUFFICIENT
    assert len(result.sources) == 2
    assert [source.citation_id for source in result.sources] == ["S1", "S2"]
    assert result.sources[0].metadata["proposal_type"] == "past_proposal"
    assert result.sources[0].metadata["page"] == 3
    assert result.sources[0].document_id == "doc-a"
    assert result.sources[0].chunk_index == 0
    assert result.sources[0].score == pytest.approx(0.93)
    assert "real-time inventory" in result.sources[0].excerpt
    assert len(result.findings) == 2
    assert len(retriever.calls) == 2
    assert llm.calls
    system_prompt, user_prompt = llm.calls[0]
    assert "Research Agent" in system_prompt
    assert "citation_id" in user_prompt
    assert "proposal_logistics.txt" in user_prompt


def test_research_without_matching_evidence_returns_insufficient_without_llm() -> None:
    llm = FakeLLM(json_response(_analysis_payload()))
    agent = ResearchAgent(
        llm=llm,
        workflows=WorkflowService(Session()),
        retriever=FakeRetriever([]),
    )

    result = agent.analyze(make_intake())

    assert result.status is ResearchStatus.INSUFFICIENT
    assert result.findings == []
    assert result.sources == []
    assert result.missing_evidence
    assert llm.calls == []


def test_research_rejects_findings_that_cite_unknown_evidence() -> None:
    payload = _analysis_payload(
        findings=[
            {
                "claim": "Unsupported claim.",
                "citation_ids": ["S99"],
                "confidence": 0.7,
            }
        ]
    )
    agent = ResearchAgent(
        llm=FakeLLM(json_response(payload)),
        workflows=WorkflowService(Session()),
        retriever=_retriever(),
    )

    with pytest.raises(InvalidResearchOutputError, match="unavailable evidence"):
        agent.analyze(make_intake())


@pytest.mark.parametrize(
    ("raw_output", "message"),
    [
        ("", "empty response"),
        ("not json", "JSON object"),
        ('[{"status": "sufficient"}]', "JSON object"),
        (
            json_response(_analysis_payload(status="sufficient", findings=[])),
            "schema validation",
        ),
    ],
)
def test_research_rejects_malformed_or_inconsistent_output(raw_output: str, message: str) -> None:
    agent = ResearchAgent(
        llm=FakeLLM(raw_output),
        workflows=WorkflowService(Session()),
        retriever=_retriever(),
    )

    with pytest.raises(InvalidResearchOutputError, match=message):
        agent.analyze(make_intake())


def test_research_process_persists_shared_state_and_moves_to_research_stage(
    database: Database,
) -> None:
    with database.session() as session:
        workflow_id = create_workflow(session)
        seed_intake(session, workflow_id)
        agent = ResearchAgent(
            llm=FakeLLM(json_response(_analysis_payload())),
            workflows=WorkflowService(session),
            retriever=_retriever(),
        )

        result = agent.process(workflow_id=workflow_id)

        service = WorkflowService(session)
        workflow = service.get_workflow(workflow_id)
        state = service.get_state(workflow_id)

    assert workflow.stage is WorkflowStage.RESEARCH
    assert workflow.status is WorkflowStatus.RUNNING
    assert workflow.state_version == 3
    assert state.research == result
    assert state.research_notes is not None
    assert "[S1]" in state.research_notes
    assert state.last_agent == "research"


def test_research_requires_a_ready_intake(database: Database) -> None:
    with database.session() as session:
        workflow_id = create_workflow(session)
        intake = make_intake(
            status="needs_clarification",
            missing_information=["Client name"],
            clarification_questions=["Who is the client?"],
        )
        service = WorkflowService(session)
        service.update_state(
            workflow_id,
            WorkflowStateUpdate(
                expected_version=1,
                status=WorkflowStatus.AWAITING_INPUT,
                intake=intake,
                extracted_requirements=intake.model_dump(mode="json"),
            ),
        )
        agent = ResearchAgent(
            llm=FakeLLM(json_response(_analysis_payload())),
            workflows=service,
            retriever=_retriever(),
        )

        with pytest.raises(ResearchRequestError, match="running workflow"):
            agent.process(workflow_id=workflow_id)
