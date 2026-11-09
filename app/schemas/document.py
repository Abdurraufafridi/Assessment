"""Structured document content and DOCX rendering result schemas."""

from datetime import date, datetime
from pathlib import Path
from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.research import SourceReference

DocumentMetadataValue = str | int | float | bool


class ParagraphBlock(BaseModel):
    """A plain body paragraph."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    type: Literal["paragraph"] = "paragraph"
    text: str = Field(min_length=1, max_length=50_000)


class HeadingBlock(BaseModel):
    """A sub-heading inside a document section."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    type: Literal["heading"] = "heading"
    level: int = Field(ge=2, le=4)
    text: str = Field(min_length=1, max_length=200)


class BulletListBlock(BaseModel):
    """An unordered list of bullet points."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    type: Literal["bullets"] = "bullets"
    items: list[str] = Field(min_length=1, max_length=100)

    @field_validator("items")
    @classmethod
    def clean_items(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip() for item in value if item.strip()]
        if not cleaned:
            raise ValueError("Bullet lists must contain at least one non-blank item")
        return cleaned


class TableBlock(BaseModel):
    """A tabular block with optional header row."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    type: Literal["table"] = "table"
    headers: list[str] | None = Field(default=None, max_length=20)
    rows: list[list[str]] = Field(min_length=1, max_length=100)
    caption: str | None = Field(default=None, max_length=200)

    @field_validator("headers")
    @classmethod
    def clean_headers(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        cleaned = [item.strip() for item in value]
        return cleaned or None

    @field_validator("rows")
    @classmethod
    def clean_rows(cls, value: list[list[str]]) -> list[list[str]]:
        if not value:
            raise ValueError("Tables must contain at least one row")
        return [[cell.strip() for cell in row] for row in value]

    @model_validator(mode="after")
    def validate_columns(self) -> Self:
        column_count = len(self.headers) if self.headers is not None else len(self.rows[0])
        if column_count == 0:
            raise ValueError("Tables must contain at least one column")
        if column_count > 20:
            raise ValueError("Tables may contain at most 20 columns")
        for row in self.rows:
            if len(row) != column_count:
                raise ValueError("Every table row must have the same number of cells")
        return self


class PageBreakBlock(BaseModel):
    """An explicit page break."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["page_break"] = "page_break"


DocumentBlock = Annotated[
    ParagraphBlock | HeadingBlock | BulletListBlock | TableBlock | PageBreakBlock,
    Field(discriminator="type"),
]


class DocumentSection(BaseModel):
    """One titled section of a generated document."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    heading: str = Field(min_length=1, max_length=200)
    subtitle: str | None = Field(default=None, max_length=200)
    blocks: list[DocumentBlock] = Field(default_factory=list, max_length=200)
    page_break_before: bool = False


class DocumentContent(BaseModel):
    """Structured content ready to render into a professional document."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    title: str = Field(min_length=1, max_length=200)
    subtitle: str | None = Field(default=None, max_length=200)
    prepared_for: str | None = Field(default=None, max_length=200)
    prepared_by: str | None = Field(default=None, max_length=200)
    document_date: date | None = None
    sections: list[DocumentSection] = Field(default_factory=list, max_length=100)
    sources: list[SourceReference] = Field(default_factory=list, max_length=100)
    include_sources: bool = True
    metadata: dict[str, DocumentMetadataValue] = Field(default_factory=dict)


class RenderedDocument(BaseModel):
    """Result of rendering content to a stored DOCX file."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    path: Path
    filename: str
    title: str
    content_hash: str = Field(min_length=64, max_length=64)
    byte_size: int = Field(ge=0)
    section_count: int = Field(ge=0)
    source_count: int = Field(ge=0)
    table_count: int = Field(ge=0)
    page_break_count: int = Field(ge=0)
    template_name: str
    rendered_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


__all__ = [
    "BulletListBlock",
    "DocumentBlock",
    "DocumentContent",
    "DocumentMetadataValue",
    "DocumentSection",
    "HeadingBlock",
    "PageBreakBlock",
    "ParagraphBlock",
    "RenderedDocument",
    "TableBlock",
]
