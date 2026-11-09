"""Validated planning and outline schemas."""

import re
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.research import CITATION_ID_PATTERN


class PlanningStatus(StrEnum):
    """Whether an outline is ready for grounded writing."""

    READY = "ready"
    NEEDS_EVIDENCE = "needs_evidence"


class OutlineSection(BaseModel):
    """One ordered section in a proposed document outline."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    heading: str = Field(min_length=1, max_length=200)
    purpose: str = Field(min_length=1, max_length=1_000)
    key_points: list[str] = Field(min_length=1, max_length=12)
    citation_ids: list[str] = Field(min_length=1, max_length=20)
    estimated_words: int = Field(ge=50, le=2_000)

    @field_validator("key_points")
    @classmethod
    def clean_key_points(cls, value: list[str]) -> list[str]:
        cleaned: list[str] = []
        for item in value:
            text = item.strip()
            if not text:
                raise ValueError("Key points must not be blank")
            if text in cleaned:
                raise ValueError("Key points must be unique")
            cleaned.append(text)
        return cleaned

    @field_validator("citation_ids")
    @classmethod
    def clean_citation_ids(cls, value: list[str]) -> list[str]:
        cleaned: list[str] = []
        for citation_id in value:
            if not re.fullmatch(CITATION_ID_PATTERN, citation_id):
                raise ValueError(
                    f"Invalid citation ID '{citation_id}'; expected the form S1, S2, ..."
                )
            if citation_id in cleaned:
                raise ValueError("Citation IDs must be unique within a section")
            cleaned.append(citation_id)
        return cleaned


class PlanningResult(BaseModel):
    """Structured outline produced from validated research evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    title: str = Field(min_length=1, max_length=200)
    sections: list[OutlineSection] = Field(min_length=1, max_length=20)
    missing_evidence: list[str] = Field(default_factory=list, max_length=20)
    status: PlanningStatus

    @field_validator("missing_evidence")
    @classmethod
    def clean_missing_evidence(cls, value: list[str]) -> list[str]:
        cleaned: list[str] = []
        for item in value:
            text = item.strip()
            if not text:
                raise ValueError("Missing-evidence items must not be blank")
            if text in cleaned:
                raise ValueError("Missing-evidence items must be unique")
            cleaned.append(text)
        return cleaned

    @model_validator(mode="after")
    def validate_outline(self) -> Self:
        headings = [section.heading for section in self.sections]
        if len(headings) != len(set(headings)):
            raise ValueError("Outline section headings must be unique")

        if self.status is PlanningStatus.READY and self.missing_evidence:
            raise ValueError("Ready outlines must not have missing evidence")
        if self.status is PlanningStatus.NEEDS_EVIDENCE and not self.missing_evidence:
            raise ValueError("Outlines needing evidence must identify what is missing")
        return self


__all__ = ["OutlineSection", "PlanningResult", "PlanningStatus"]
