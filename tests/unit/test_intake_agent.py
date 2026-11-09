"""Tests for the Phase 3 intake agent and its state persistence."""

import json
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from app.agents.errors import IntakeRequestError, InvalidIntakeOutputError
from app.agents.intake import IntakeAgent
from app.db.database import Database
from app.domain.enums import WorkflowStatus
from app.repositories.users import UserRepository
from app.schemas.intake import DeliverableType, IntakeResult, IntakeStatus
from app.services.workflows import WorkflowService

pytestmark = pytest.mark.unit


class FakeLLM:
    """Deterministic LLM double that records prompts."""

    provider_name = "fake"
    model_name = "fake-intake"

    def __init__(self, response: str) -> None:
        self.response = response
        self.calls: list[tuple[str, str]] = []

    def generate(self, *, system_prompt: str, user_prompt: str) -> str:
        self.calls.append((system_prompt, user_prompt))
        return self.response


def _payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "objective": "Create a proposal for Acme's warehouse modernization.",
        "document_type": "proposal",
        "document_subtype": "technical proposal",
        "audience": "Acme operations leadership",
        "required_inputs": ["Discovery transcript", "Budget range"],
        "constraints": ["Maximum 8 pages", "Complete by 2026-12-01"],
        "missing_information": [],
        "clarification_questions": [],
        "status": "ready",
        "confidence": 0.92,
    }
    payload.update(overrides)
    return payload


def _json_response(payload: dict[str, Any], *, fenced: bool = False) -> str:
    encoded = json.dumps(payload)
    return f"```json\n{encoded}\n```" if fenced else encoded


def _create_workflow(session: Session) -> str:
    user = UserRepository(session).create(
        slack_user_id=f"U-{uuid4().hex[:8]}",
        display_name="Intake User",
    )
    workflow = WorkflowService(session).create_workflow(user_id=user.id)
    return workflow.id


def test_normal_request_produces_ready_intake_and_persists_state(database: Database) -> None:
    with database.session() as session:
        workflow_id = _create_workflow(session)
        llm = FakeLLM(_json_response(_payload(), fenced=True))
        agent = IntakeAgent(llm=llm, workflows=WorkflowService(session))

        result = agent.process(
            workflow_id=workflow_id,
            request="Create an 8-page technical proposal for Acme's warehouse modernization.",
        )
        session.commit()

    assert result.status is IntakeStatus.READY
    assert result.document_type is DeliverableType.PROPOSAL
    assert result.clarification_questions == []

    with database.session() as session:
        service = WorkflowService(session)
        workflow = service.get_workflow(workflow_id)
        state = service.get_state(workflow_id)

    assert workflow.status == WorkflowStatus.RUNNING
    assert workflow.state_version == 2
    assert state.intake == result
    assert state.extracted_requirements["objective"] == result.objective
    assert state.last_agent == "intake"


def test_incomplete_request_asks_clarification_and_awaits_input(database: Database) -> None:
    payload = _payload(
        objective="Create a proposal for a client.",
        required_inputs=["Client name", "Project scope", "Budget"],
        constraints=[],
        missing_information=["Client name", "Project scope", "Budget"],
        clarification_questions=[
            "Who is the client?",
            "What is the project scope?",
            "What budget range should the proposal target?",
        ],
        status="needs_clarification",
        confidence=0.35,
    )
    with database.session() as session:
        workflow_id = _create_workflow(session)
        agent = IntakeAgent(
            llm=FakeLLM(_json_response(payload)),
            workflows=WorkflowService(session),
        )

        result = agent.process(
            workflow_id=workflow_id,
            request="Please write a proposal for the client.",
        )
        service = WorkflowService(session)
        workflow = service.get_workflow(workflow_id)
        state = service.get_state(workflow_id)

    assert result.status is IntakeStatus.NEEDS_CLARIFICATION
    assert result.missing_information == payload["missing_information"]
    assert len(result.clarification_questions) == 3
    assert workflow.status == WorkflowStatus.AWAITING_INPUT
    assert state.intake == result


def test_ambiguous_request_asks_for_deliverable_clarification(database: Database) -> None:
    payload = _payload(
        objective="Create the requested document.",
        document_type="other",
        document_subtype=None,
        audience=None,
        required_inputs=[],
        constraints=[],
        missing_information=["Deliverable type", "Target audience"],
        clarification_questions=[
            "Do you need a proposal, report, or plan?",
            "Who is the intended audience?",
        ],
        status="needs_clarification",
        confidence=0.2,
    )
    with database.session() as session:
        workflow_id = _create_workflow(session)
        agent = IntakeAgent(
            llm=FakeLLM(_json_response(payload)),
            workflows=WorkflowService(session),
        )

        result = agent.process(workflow_id=workflow_id, request="Make the document for them.")
        workflow = WorkflowService(session).get_workflow(workflow_id)

    assert result.document_type is DeliverableType.OTHER
    assert result.status is IntakeStatus.NEEDS_CLARIFICATION
    assert result.clarification_questions[0].startswith("Do you need")
    assert workflow.status == WorkflowStatus.AWAITING_INPUT


def test_follow_up_answers_clear_clarification_state(database: Database) -> None:
    incomplete = _payload(
        status="needs_clarification",
        missing_information=["Client name"],
        clarification_questions=["Who is the client?"],
        confidence=0.4,
    )
    with database.session() as session:
        workflow_id = _create_workflow(session)
        first_agent = IntakeAgent(
            llm=FakeLLM(_json_response(incomplete)),
            workflows=WorkflowService(session),
        )
        first = first_agent.process(workflow_id=workflow_id, request="Write a proposal.")
        session.commit()

    with database.session() as session:
        second_agent = IntakeAgent(
            llm=FakeLLM(_json_response(_payload())),
            workflows=WorkflowService(session),
        )
        second = second_agent.process(
            workflow_id=workflow_id,
            request="The client is Acme Corporation.",
        )
        service = WorkflowService(session)
        workflow = service.get_workflow(workflow_id)
        state = service.get_state(workflow_id)

    assert first.status is IntakeStatus.NEEDS_CLARIFICATION
    assert second.status is IntakeStatus.READY
    assert workflow.status == WorkflowStatus.RUNNING
    assert workflow.state_version == 3
    assert state.intake == second
    assert state.intake is not None
    assert state.intake.clarification_questions == []


def test_previous_intake_is_included_for_follow_up_clarification(database: Database) -> None:
    previous = IntakeResult.model_validate(
        _payload(
            status="needs_clarification",
            missing_information=["Client name"],
            clarification_questions=["Who is the client?"],
            confidence=0.4,
        )
    )
    with database.session() as session:
        llm = FakeLLM(_json_response(_payload()))
        agent = IntakeAgent(llm=llm, workflows=WorkflowService(session))
        result = agent.analyze("The client is Acme Corporation.", previous_intake=previous)

    assert result.status is IntakeStatus.READY
    assert len(llm.calls) == 1
    system_prompt, user_prompt = llm.calls[0]
    assert "Intake Agent" in system_prompt
    assert "Previously validated intake result" in user_prompt
    assert previous.objective in user_prompt
    assert "The client is Acme Corporation." in user_prompt


@pytest.mark.parametrize(
    ("raw_output", "message"),
    [
        ("not json at all", "JSON object"),
        ("", "empty response"),
        ('[{"objective": "wrong shape"}]', "JSON object"),
        (_json_response(_payload(document_type="email")), "schema validation"),
        (
            _json_response(_payload(clarification_questions=["Why?"])),
            "schema validation",
        ),
        (_json_response(_payload(objective="   ")), "schema validation"),
    ],
)
def test_invalid_llm_outputs_are_rejected(
    database: Database, raw_output: str, message: str
) -> None:
    with database.session() as session:
        agent = IntakeAgent(
            llm=FakeLLM(raw_output),
            workflows=WorkflowService(session),
        )

        with pytest.raises(InvalidIntakeOutputError, match=message):
            agent.analyze("Create a proposal.")


def test_invalid_output_does_not_change_workflow_state(database: Database) -> None:
    with database.session() as session:
        workflow_id = _create_workflow(session)
        agent = IntakeAgent(
            llm=FakeLLM(_json_response(_payload(status="unknown"))),
            workflows=WorkflowService(session),
        )

        with pytest.raises(InvalidIntakeOutputError):
            agent.process(workflow_id=workflow_id, request="Create a proposal.")

        service = WorkflowService(session)
        workflow = service.get_workflow(workflow_id)
        state = service.get_state(workflow_id)

    assert workflow.state_version == 1
    assert workflow.status == WorkflowStatus.PENDING
    assert state.intake is None
    assert state.last_agent is None


def test_blank_request_is_rejected_before_calling_the_llm(database: Database) -> None:
    with database.session() as session:
        llm = FakeLLM(_json_response(_payload()))
        agent = IntakeAgent(llm=llm, workflows=WorkflowService(session))

        with pytest.raises(IntakeRequestError, match="must not be blank"):
            agent.analyze("   ")

        assert llm.calls == []
