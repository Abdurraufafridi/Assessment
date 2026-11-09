"""Validated research findings, evidence, and source-reference schemas."""

import re
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SourceMetadataValue = str | int | float | bool
CITATION_ID_PATTERN = r"^S[1-9][0-9]*$"


class ResearchStatus(StrEnum):
    """Whether the evidence is sufficient to support planning and writing."""

    SUFFICIENT = "sufficient"
    INSUFFICIENT = "insufficient"


class SourceReference(BaseModel):
    """A retrieved chunk and the metadata required to cite it faithfully."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    citation_id: str = Field(pattern=CITATION_ID_PATTERN)
    chunk_id: str = Field(min_length=1, max_length=255)
    document_id: str = Field(min_length=1, max_length=36)
    source_name: str = Field(min_length=1, max_length=255)
    source_type: str | None = Field(default=None, max_length=50)
    chunk_index: int | None = Field(default=None, ge=0)
    score: float | None = None
    excerpt: str = Field(min_length=1, max_length=6_000)
    metadata: dict[str, SourceMetadataValue] = Field(default_factory=dict)


class ResearchFinding(BaseModel):
    """One evidence-backed claim produced by the research agent."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    claim: str = Field(min_length=1, max_length=2_000)
    citation_ids: list[str] = Field(min_length=1, max_length=20)
    confidence: float = Field(ge=0.0, le=1.0)

    @field_validator("citation_ids")
    @classmethod
    def citation_ids_must_be_valid_and_unique(cls, value: list[str]) -> list[str]:
        cleaned: list[str] = []
        for citation_id in value:
            if not re.fullmatch(CITATION_ID_PATTERN, citation_id):
                raise ValueError(
                    f"Invalid citation ID '{citation_id}'; expected the form S1, S2, ..."
                )
            if citation_id in cleaned:
                raise ValueError("Citation IDs must be unique within a finding")
            cleaned.append(citation_id)
        return cleaned


class ResearchAnalysis(BaseModel):
    """The structured research output requested from the LLM."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    status: ResearchStatus
    findings: list[ResearchFinding] = Field(default_factory=list, max_length=30)
    missing_evidence: list[str] = Field(default_factory=list, max_length=20)
    coverage: float = Field(ge=0.0, le=1.0)

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
    def validate_status(self) -> Self:
        if self.status is ResearchStatus.SUFFICIENT and not self.findings:
            raise ValueError("Sufficient research requires at least one finding")
        if self.status is ResearchStatus.INSUFFICIENT and not self.missing_evidence:
            raise ValueError("Insufficient research must identify missing evidence")
        return self


class ResearchResult(ResearchAnalysis):
    """Validated research state with retrieval provenance."""

    queries: list[str] = Field(min_length=1, max_length=5)
    sources: list[SourceReference] = Field(default_factory=list, max_length=30)

    @field_validator("queries")
    @classmethod
    def clean_queries(cls, value: list[str]) -> list[str]:
        cleaned: list[str] = []
        for item in value:
            text = item.strip()
            if not text:
                raise ValueError("Research queries must not be blank")
            if text in cleaned:
                raise ValueError("Research queries must be unique")
            cleaned.append(text)
        return cleaned

    @model_validator(mode="after")
    def validate_sources_and_citations(self) -> Self:
        citation_ids = [source.citation_id for source in self.sources]
        chunk_ids = [source.chunk_id for source in self.sources]
        if len(citation_ids) != len(set(citation_ids)):
            raise ValueError("Source citation IDs must be unique")
        if len(chunk_ids) != len(set(chunk_ids)):
            raise ValueError("Source chunk IDs must be unique")

        known = set(citation_ids)
        for finding in self.findings:
            unknown = set(finding.citation_ids) - known
            if unknown:
                raise ValueError(
                    "Findings reference unknown source citations: " + ", ".join(sorted(unknown))
                )

        if self.status is ResearchStatus.SUFFICIENT and not self.sources:
            raise ValueError("Sufficient research requires at least one source")
        return self

    def source_map(self) -> dict[str, SourceReference]:
        """Return sources keyed by their stable citation ID."""

        return {source.citation_id: source for source in self.sources}


__all__ = [
    "CITATION_ID_PATTERN",
    "ResearchAnalysis",
    "ResearchFinding",
    "ResearchResult",
    "ResearchStatus",
    "SourceMetadataValue",
    "SourceReference",
]
