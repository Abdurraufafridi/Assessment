"""Independent tests for the Phase 4 planning agent."""

from typing import Any

import pytest
from sqlalchemy.orm import Session

from app.agents.errors import InvalidPlanningOutputError, PlanningRequestError
from app.agents.planning import PlanningAgent
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
    seed_intake,
    seed_research,
)

pytestmark = pytest.mark.unit


class FakeLLM:
    provider_name = "fake"
    model_name = "fake-planning"

    def __init__(self, response: str) -> None:
        self.response = response
        self.calls: list[tuple[str, str]] = []

    def generate(self, *, system_prompt: str, user_prompt: str) -> str:
        self.calls.append((system_prompt, user_prompt))
        return self.response


def _plan_payload(**overrides: Any) -> dict[str, Any]:
    payload = make_outline().model_dump(mode="json")
    payload.update(overrides)
    return payload


def test_planning_builds_a_structured_evidenced_outline() -> None:
    llm = FakeLLM(json_response(_plan_payload(), fenced=True))
    agent = PlanningAgent(llm=llm, workflows=WorkflowService(Session()))

    result = agent.analyze(make_intake(), make_research())

    assert result.status is PlanningStatus.READY
    assert [section.heading for section in result.sections] == [
        "Client Needs",
        "Delivery Approach",
    ]
    assert [section.citation_ids for section in result.sections] == [["S1"], ["S2"]]
    assert result.missing_evidence == []
    system_prompt, user_prompt = llm.calls[0]
    assert "Planning Agent" in system_prompt
    assert "Validated research" in user_prompt
    assert "source_name" in user_prompt


def test_planning_can_identify_missing_evidence() -> None:
    payload = _plan_payload(
        status="needs_evidence",
        missing_evidence=["Current warehouse throughput baseline"],
        sections=[
            {
                "heading": "Client Needs",
                "purpose": "Summarize the validated client requirements.",
                "key_points": ["Modernize warehouse operations"],
                "citation_ids": ["S1"],
                "estimated_words": 250,
            }
        ],
    )
    agent = PlanningAgent(
        llm=FakeLLM(json_response(payload)),
        workflows=WorkflowService(Session()),
    )

    result = agent.analyze(make_intake(), make_research())

    assert result.status is PlanningStatus.NEEDS_EVIDENCE
    assert result.missing_evidence == ["Current warehouse throughput baseline"]


def test_planning_rejects_citations_not_present_in_research() -> None:
    payload = _plan_payload(
        sections=[
            {
                "heading": "Client Needs",
                "purpose": "Summarize the validated client requirements.",
                "key_points": ["Modernize warehouse operations"],
                "citation_ids": ["S99"],
                "estimated_words": 250,
            }
        ]
    )
    agent = PlanningAgent(
        llm=FakeLLM(json_response(payload)),
        workflows=WorkflowService(Session()),
    )

    with pytest.raises(InvalidPlanningOutputError, match="unavailable evidence"):
        agent.analyze(make_intake(), make_research())


def test_planning_cannot_approve_an_outline_from_insufficient_research() -> None:
    research = make_research(
        status=ResearchStatus.INSUFFICIENT,
        missing_evidence=["Current warehouse throughput baseline"],
    )
    agent = PlanningAgent(
        llm=FakeLLM(json_response(_plan_payload())),
        workflows=WorkflowService(Session()),
    )

    with pytest.raises(InvalidPlanningOutputError, match="research is insufficient"):
        agent.analyze(make_intake(), research)


@pytest.mark.parametrize(
    ("raw_output", "message"),
    [
        ("", "empty response"),
        ("not json", "JSON object"),
        (
            json_response(_plan_payload(status="ready", missing_evidence=["gap"])),
            "schema validation",
        ),
        (
            json_response(
                _plan_payload(
                    status="needs_evidence",
                    missing_evidence=[],
                )
            ),
            "schema validation",
        ),
    ],
)
def test_planning_rejects_malformed_or_inconsistent_output(raw_output: str, message: str) -> None:
    agent = PlanningAgent(
        llm=FakeLLM(raw_output),
        workflows=WorkflowService(Session()),
    )

    with pytest.raises(InvalidPlanningOutputError, match=message):
        agent.analyze(make_intake(), make_research())


def test_planning_process_persists_outline_in_shared_state(database: Database) -> None:
    with database.session() as session:
        workflow_id = create_workflow(session)
        seed_research(session, workflow_id)
        agent = PlanningAgent(
            llm=FakeLLM(json_response(_plan_payload())),
            workflows=WorkflowService(session),
        )

        result = agent.process(workflow_id=workflow_id)

        service = WorkflowService(session)
        workflow = service.get_workflow(workflow_id)
        state = service.get_state(workflow_id)

    assert workflow.stage is WorkflowStage.RESEARCH
    assert workflow.state_version == 3
    assert state.outline == result
    assert state.last_agent == "planning"
    assert state.research is not None


def test_planning_requires_prior_research(database: Database) -> None:
    with database.session() as session:
        workflow_id = create_workflow(session)
        seed_intake(session, workflow_id)
        agent = PlanningAgent(
            llm=FakeLLM(json_response(_plan_payload())),
            workflows=WorkflowService(session),
        )

        with pytest.raises(PlanningRequestError, match="no research result"):
            agent.process(workflow_id=workflow_id)
