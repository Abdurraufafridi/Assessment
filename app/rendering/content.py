"""Adapters that turn generated writing output into renderable content."""

from datetime import date

from app.rendering.parser import blocks_from_text
from app.schemas.document import (
    DocumentContent,
    DocumentMetadataValue,
    DocumentSection,
)
from app.schemas.writing import WritingResult


def content_from_writing(
    writing: WritingResult,
    *,
    subtitle: str | None = None,
    prepared_for: str | None = None,
    prepared_by: str | None = None,
    document_date: date | None = None,
    include_sources: bool = True,
    metadata: dict[str, DocumentMetadataValue] | None = None,
) -> DocumentContent:
    """Convert a validated writing result into structured document content."""

    sections = [
        DocumentSection(
            heading=section.heading,
            blocks=blocks_from_text(section.content),
        )
        for section in writing.sections
    ]
    return DocumentContent(
        title=writing.title,
        subtitle=subtitle,
        prepared_for=prepared_for,
        prepared_by=prepared_by,
        document_date=document_date,
        sections=sections,
        sources=list(writing.sources),
        include_sources=include_sources,
        metadata=metadata or {},
    )


__all__ = ["content_from_writing"]
