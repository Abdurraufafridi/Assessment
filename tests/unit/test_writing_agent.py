"""Independent tests for the Phase 4 writing agent."""

from typing import Any

import pytest
from sqlalchemy.orm import Session

from app.agents.errors import InvalidWritingOutputError, WritingRequestError
from app.agents.writing import WritingAgent
from app.db.database import Database
from app.domain.enums import WorkflowStage
from app.schemas.planning import PlanningStatus
from app.schemas.research import ResearchStatus
from app.services.workflows import WorkflowService
from tests.unit.phase4_helpers import (
    create_workflow,
    json_response,
    make_intake,
    make_outline,
    make_research,
    seed_outline,
)

pytestmark = pytest.mark.unit


class FakeLLM:
    provider_name = "fake"
    model_name = "fake-writing"

    def __init__(self, response: str) -> None:
        self.response = response
        self.calls: list[tuple[str, str]] = []

    def generate(self, *, system_prompt: str, user_prompt: str) -> str:
        self.calls.append((system_prompt, user_prompt))
        return self.response


def _writing_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "title": "Acme Warehouse Modernization Proposal",
        "sections": [
            {
                "heading": "Client Needs",
                "content": "Acme needs real-time inventory visibility [S1].",
                "citation_ids": ["S1"],
            },
            {
                "heading": "Delivery Approach",
                "content": "We recommend a phased rollout [S2].",
                "citation_ids": ["S2"],
            },
        ],
    }
    payload.update(overrides)
    return payload


def _agent(response: str) -> WritingAgent:
    return WritingAgent(
        llm=FakeLLM(response),
        workflows=WorkflowService(Session()),
    )


def test_writing_generates_grounded_sections_and_preserves_sources() -> None:
    llm = FakeLLM(json_response(_writing_payload(), fenced=True))
    agent = WritingAgent(llm=llm, workflows=WorkflowService(Session()))

    result = agent.analyze(make_intake(), make_research(), make_outline())

    assert [section.heading for section in result.sections] == [
        "Client Needs",
        "Delivery Approach",
    ]
    assert [source.citation_id for source in result.sources] == ["S1", "S2"]
    assert result.sources[0].source_name == "s1.txt"
    assert result.sources[0].metadata["industry"] == "logistics"
    markdown = result.render_markdown()
    assert "## Sources" in markdown
    assert "[S1]" in markdown
    assert "s1.txt" in markdown
    system_prompt, user_prompt = llm.calls[0]
    assert "Writing Agent" in system_prompt
    assert "Approved outline" in user_prompt
    assert "Approved research" in user_prompt


def test_writing_rejects_citations_that_are_not_in_research() -> None:
    payload = _writing_payload(
        sections=[
            {
                "heading": "Client Needs",
                "content": "Acme needs real-time inventory visibility [S99].",
                "citation_ids": ["S99"],
            },
            {
                "heading": "Delivery Approach",
                "content": "We recommend a phased rollout [S2].",
                "citation_ids": ["S2"],
            },
        ]
    )
    agent = _agent(json_response(payload))

    with pytest.raises(InvalidWritingOutputError, match="unavailable evidence"):
        agent.analyze(make_intake(), make_research(), make_outline())


def test_writing_rejects_evidence_not_approved_for_a_section() -> None:
    payload = _writing_payload(
        sections=[
            {
                "heading": "Client Needs",
                "content": "Acme needs real-time inventory visibility [S2].",
                "citation_ids": ["S2"],
            },
            {
                "heading": "Delivery Approach",
                "content": "We recommend a phased rollout [S2].",
                "citation_ids": ["S2"],
            },
        ]
    )
    agent = _agent(json_response(payload))

    with pytest.raises(InvalidWritingOutputError, match="not approved for that section"):
        agent.analyze(make_intake(), make_research(), make_outline())


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (
            _writing_payload(
                sections=[
                    {
                        "heading": "Client Needs",
                        "content": "Acme needs real-time inventory visibility [1].",
                        "citation_ids": ["S1"],
                    },
                    {
                        "heading": "Delivery Approach",
                        "content": "We recommend a phased rollout [S2].",
                        "citation_ids": ["S2"],
                    },
                ]
            ),
            "Numeric citation",
        ),
        (
            _writing_payload(title="Different Proposal"),
            "title must match",
        ),
        (
            _writing_payload(
                sections=[
                    {
                        "heading": "Delivery Approach",
                        "content": "We recommend a phased rollout [S2].",
                        "citation_ids": ["S2"],
                    },
                    {
                        "heading": "Client Needs",
                        "content": "Acme needs real-time inventory visibility [S1].",
                        "citation_ids": ["S1"],
                    },
                ]
            ),
            "headings and order",
        ),
        (
            _writing_payload(
                sections=[
                    {
                        "heading": "Client Needs",
                        "content": "Acme needs real-time inventory visibility.",
                        "citation_ids": ["S1"],
                    },
                    {
                        "heading": "Delivery Approach",
                        "content": "We recommend a phased rollout [S2].",
                        "citation_ids": ["S2"],
                    },
                ]
            ),
            "Declared citations do not appear",
        ),
    ],
)
def test_writing_rejects_unsupported_or_out_of_plan_content(
    payload: dict[str, Any], message: str
) -> None:
    agent = _agent(json_response(payload))

    with pytest.raises(InvalidWritingOutputError, match=message):
        agent.analyze(make_intake(), make_research(), make_outline())


def test_writing_requires_sufficient_research_and_a_ready_outline() -> None:
    insufficient_research = make_research(
        status=ResearchStatus.INSUFFICIENT,
        missing_evidence=["Current throughput baseline"],
    )
    agent = _agent(json_response(_writing_payload()))

    with pytest.raises(WritingRequestError, match="sufficient research"):
        agent.analyze(make_intake(), insufficient_research, make_outline())

    needs_evidence_outline = make_outline(
        status=PlanningStatus.NEEDS_EVIDENCE,
        missing_evidence=["Current throughput baseline"],
    )
    with pytest.raises(WritingRequestError, match="ready outline"):
        agent.analyze(make_intake(), make_research(), needs_evidence_outline)


def test_writing_process_persists_draft_in_shared_state(database: Database) -> None:
    with database.session() as session:
        workflow_id = create_workflow(session)
        seed_outline(session, workflow_id)
        agent = WritingAgent(
            llm=FakeLLM(json_response(_writing_payload())),
            workflows=WorkflowService(session),
        )

        result = agent.process(workflow_id=workflow_id)

        service = WorkflowService(session)
        workflow = service.get_workflow(workflow_id)
        state = service.get_state(workflow_id)

    assert workflow.stage is WorkflowStage.WRITING
    assert workflow.state_version == 3
    assert state.draft == result
    assert state.last_agent == "writing"
    assert state.research is not None
    assert state.outline is not None
