"""Validated intake and requirement-understanding schemas."""

from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class IntakeStatus(StrEnum):
    """Whether enough information exists to continue the workflow."""

    READY = "ready"
    NEEDS_CLARIFICATION = "needs_clarification"


class DeliverableType(StrEnum):
    """Document or report category requested by the user."""

    PROPOSAL = "proposal"
    REPORT = "report"
    PLAN = "plan"
    SUMMARY = "summary"
    ANALYSIS = "analysis"
    OTHER = "other"


class IntakeResult(BaseModel):
    """Structured result of the intake conversation.

    This is the contract between the intake agent and the rest of the workflow.
    It deliberately contains only requirement-understanding data: no research,
    writing, or execution decisions belong here.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    objective: str = Field(min_length=1, max_length=2_000)
    document_type: DeliverableType
    document_subtype: str | None = Field(default=None, max_length=120)
    audience: str | None = Field(default=None, max_length=255)
    required_inputs: list[str] = Field(default_factory=list, max_length=20)
    constraints: list[str] = Field(default_factory=list, max_length=30)
    missing_information: list[str] = Field(default_factory=list, max_length=20)
    clarification_questions: list[str] = Field(default_factory=list, max_length=10)
    status: IntakeStatus
    confidence: float = Field(ge=0.0, le=1.0)

    @field_validator("document_subtype", "audience")
    @classmethod
    def blank_optional_text_is_none(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @field_validator(
        "required_inputs",
        "constraints",
        "missing_information",
        "clarification_questions",
    )
    @classmethod
    def clean_text_lists(cls, value: list[str]) -> list[str]:
        cleaned: list[str] = []
        for item in value:
            text = item.strip()
            if not text:
                raise ValueError("Intake list items must not be blank")
            if text in cleaned:
                raise ValueError("Intake list items must be unique")
            cleaned.append(text)
        return cleaned

    @model_validator(mode="after")
    def validate_clarification_state(self) -> Self:
        if self.status is IntakeStatus.READY and self.clarification_questions:
            raise ValueError("Ready intake results must not include clarification questions")
        if self.status is IntakeStatus.NEEDS_CLARIFICATION and not self.clarification_questions:
            raise ValueError("Clarification is required when intake is not ready")
        return self


__all__ = ["DeliverableType", "IntakeResult", "IntakeStatus"]
