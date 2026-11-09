"""Sequential research, planning, and writing orchestration."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.agents.planning import PlanningAgent
from app.agents.research import ResearchAgent
from app.agents.writing import WritingAgent
from app.core.config import Settings
from app.llm.factory import create_llm_provider
from app.schemas.planning import PlanningResult
from app.schemas.research import ResearchResult
from app.schemas.writing import WritingResult
from app.services.retrieval import RagRetriever
from app.services.workflows import WorkflowService


@dataclass(frozen=True, slots=True)
class Phase4Result:
    """Shared-state results produced by the research, planning, and writing agents."""

    research: ResearchResult
    outline: PlanningResult
    draft: WritingResult


class ProposalPipeline:
    """Run the Phase 4 agents in order using one shared workflow state."""

    def __init__(
        self,
        *,
        research: ResearchAgent,
        planning: PlanningAgent,
        writing: WritingAgent,
    ) -> None:
        self._research = research
        self._planning = planning
        self._writing = writing

    @classmethod
    def from_settings(cls, *, session: Session, settings: Settings) -> ProposalPipeline:
        """Build the pipeline with one LLM provider and the configured RAG stack."""

        llm = create_llm_provider(settings)
        workflows = WorkflowService(session)
        return cls(
            research=ResearchAgent(
                llm=llm,
                workflows=workflows,
                retriever=RagRetriever.from_settings(settings),
            ),
            planning=PlanningAgent(llm=llm, workflows=workflows),
            writing=WritingAgent(llm=llm, workflows=workflows),
        )

    def run(
        self,
        *,
        workflow_id: str,
        extra_queries: Sequence[str] | None = None,
    ) -> Phase4Result:
        """Run research, planning, and writing in sequence without committing."""

        research = self._research.process(
            workflow_id=workflow_id,
            extra_queries=extra_queries,
        )
        outline = self._planning.process(workflow_id=workflow_id)
        draft = self._writing.process(workflow_id=workflow_id)
        return Phase4Result(research=research, outline=outline, draft=draft)


__all__ = ["Phase4Result", "ProposalPipeline"]
