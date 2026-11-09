"""Integration test: research, planning, and writing share workflow state."""

from collections.abc import Mapping
from typing import Any

import pytest

from app.agents.pipeline import ProposalPipeline
from app.agents.planning import PlanningAgent
from app.agents.research import ResearchAgent
from app.agents.writing import WritingAgent
from app.db.database import Database
from app.domain.enums import WorkflowStage, WorkflowStatus
from app.ingestion.metadata import MetadataValue
from app.services.workflows import WorkflowService
from app.vectorstore.base import VectorSearchResult
from tests.unit.phase4_helpers import (
    create_workflow,
    json_response,
    make_outline,
    seed_intake,
)

pytestmark = pytest.mark.integration


class SequenceLLM:
    provider_name = "fake"
    model_name = "fake-phase4"

    def __init__(self, responses: list[str]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, str]] = []

    def generate(self, *, system_prompt: str, user_prompt: str) -> str:
        self.calls.append((system_prompt, user_prompt))
        return self.responses[len(self.calls) - 1]


class FakeRetriever:
    def __init__(self, results: list[VectorSearchResult]) -> None:
        self.results = results

    def search(
        self,
        query: str,
        *,
        top_k: int = 6,
        where: Mapping[str, MetadataValue] | None = None,
    ) -> list[VectorSearchResult]:
        del query, top_k, where
        return self.results


def _research_result() -> VectorSearchResult:
    return VectorSearchResult(
        id="doc-a:0000",
        text="Acme needs real-time inventory visibility across its warehouses.",
        metadata={
            "document_id": "doc-a",
            "source_name": "proposal_logistics.txt",
            "source_type": "txt",
            "chunk_index": 0,
            "industry": "logistics",
        },
        distance=0.1,
        score=0.9,
    )


def _research_payload() -> dict[str, Any]:
    return {
        "status": "sufficient",
        "findings": [
            {
                "claim": "Acme needs real-time inventory visibility.",
                "citation_ids": ["S1"],
                "confidence": 0.9,
            }
        ],
        "missing_evidence": [],
        "coverage": 0.85,
    }


def _writing_payload() -> dict[str, Any]:
    return {
        "title": "Acme Warehouse Modernization Proposal",
        "sections": [
            {
                "heading": "Client Needs",
                "content": "Acme needs real-time inventory visibility [S1].",
                "citation_ids": ["S1"],
            },
            {
                "heading": "Delivery Approach",
                "content": "The evidence supports a phased rollout [S1].",
                "citation_ids": ["S1"],
            },
        ],
    }


def test_phase4_pipeline_persists_all_agent_outputs(database: Database) -> None:
    outline_payload = make_outline().model_dump(mode="json")
    outline_payload["sections"][1]["citation_ids"] = ["S1"]
    llm = SequenceLLM(
        [
            json_response(_research_payload()),
            json_response(outline_payload),
            json_response(_writing_payload()),
        ]
    )

    with database.session() as session:
        workflow_id = create_workflow(session)
        seed_intake(session, workflow_id)
        workflows = WorkflowService(session)
        pipeline = ProposalPipeline(
            research=ResearchAgent(
                llm=llm,
                workflows=workflows,
                retriever=FakeRetriever([_research_result()]),
            ),
            planning=PlanningAgent(llm=llm, workflows=workflows),
            writing=WritingAgent(llm=llm, workflows=workflows),
        )

        result = pipeline.run(workflow_id=workflow_id)
        session.commit()

        workflow = workflows.get_workflow(workflow_id)
        state = workflows.get_state(workflow_id)

    assert len(llm.calls) == 3
    assert result.research.status.value == "sufficient"
    assert result.outline.status.value == "ready"
    assert len(result.draft.sections) == 2
    assert workflow.stage is WorkflowStage.WRITING
    assert workflow.status is WorkflowStatus.RUNNING
    assert workflow.state_version == 5
    assert state.research == result.research
    assert state.outline == result.outline
    assert state.draft == result.draft
    assert state.last_agent == "writing"
    assert state.research_notes is not None
    assert "proposal_logistics.txt" in state.research_notes
    assert result.draft.sources[0].metadata["industry"] == "logistics"


def test_phase4_pipeline_stops_before_writing_when_evidence_is_missing(
    database: Database,
) -> None:
    from app.agents.errors import InvalidPlanningOutputError

    outline_payload = make_outline().model_dump(mode="json")
    outline_payload["status"] = "ready"
    for section in outline_payload["sections"]:
        section["citation_ids"] = ["S1"]
    llm = SequenceLLM(
        [
            json_response(
                {
                    "status": "insufficient",
                    "findings": [],
                    "missing_evidence": ["Current warehouse throughput baseline"],
                    "coverage": 0.2,
                }
            ),
            json_response(outline_payload),
        ]
    )

    with database.session() as session:
        workflow_id = create_workflow(session)
        seed_intake(session, workflow_id)
        workflows = WorkflowService(session)
        pipeline = ProposalPipeline(
            research=ResearchAgent(
                llm=llm,
                workflows=workflows,
                retriever=FakeRetriever([_research_result()]),
            ),
            planning=PlanningAgent(llm=llm, workflows=workflows),
            writing=WritingAgent(llm=llm, workflows=workflows),
        )

        with pytest.raises(InvalidPlanningOutputError, match="research is insufficient"):
            pipeline.run(workflow_id=workflow_id)

    assert len(llm.calls) == 2
