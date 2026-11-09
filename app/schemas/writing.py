"""Validated writing output and citation schemas."""

import re
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.research import CITATION_ID_PATTERN, SourceReference

_CITATION_MARKER_RE = re.compile(r"\[(S[1-9][0-9]*|[0-9]+)\]")


class WritingSection(BaseModel):
    """One grounded section of the generated draft."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    heading: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=20_000)
    citation_ids: list[str] = Field(min_length=1, max_length=20)

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

    @model_validator(mode="after")
    def validate_citation_markers(self) -> Self:
        markers: list[str] = []
        for match in _CITATION_MARKER_RE.finditer(self.content):
            marker = match.group(1)
            if not marker.startswith("S"):
                raise ValueError(
                    f"Numeric citation '[{marker}]' is not allowed; use [S1], [S2], ..."
                )
            markers.append(marker)

        declared = set(self.citation_ids)
        used = set(markers)
        if used - declared:
            raise ValueError(
                "Section content cites undeclared sources: " + ", ".join(sorted(used - declared))
            )
        if declared - used:
            raise ValueError(
                "Declared citations do not appear in the section: "
                + ", ".join(sorted(declared - used))
            )
        return self


class WritingResult(BaseModel):
    """Validated draft content and the exact sources used to ground it."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    title: str = Field(min_length=1, max_length=200)
    sections: list[WritingSection] = Field(min_length=1, max_length=20)
    sources: list[SourceReference] = Field(default_factory=list, max_length=30)

    @model_validator(mode="after")
    def validate_sources(self) -> Self:
        headings = [section.heading for section in self.sections]
        if len(headings) != len(set(headings)):
            raise ValueError("Writing section headings must be unique")

        source_ids = [source.citation_id for source in self.sources]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("Writing sources must be unique")

        known = set(source_ids)
        cited = {citation_id for section in self.sections for citation_id in section.citation_ids}
        if cited - known:
            raise ValueError(
                "Writing cites sources that are not in its source list: "
                + ", ".join(sorted(cited - known))
            )
        if known - cited:
            raise ValueError(
                "Writing source list contains sources that are not cited: "
                + ", ".join(sorted(known - cited))
            )
        return self

    def render_markdown(self) -> str:
        """Render the draft with a deterministic source-reference section."""

        lines = [f"# {self.title}", ""]
        for section in self.sections:
            lines.extend([f"## {section.heading}", "", section.content, ""])

        if self.sources:
            lines.extend(["## Sources", ""])
            for source in self.sources:
                location = source.source_name
                if source.chunk_index is not None:
                    location += f", chunk {source.chunk_index}"
                lines.append(f"- [{source.citation_id}] {location} ({source.document_id})")
            lines.append("")
        return "\n".join(lines).rstrip() + "\n"


__all__ = ["WritingResult", "WritingSection"]
