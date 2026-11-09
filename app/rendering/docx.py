"""Professional DOCX rendering for structured proposal content."""

from __future__ import annotations

import hashlib
import os
import re
import tempfile
import unicodedata
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from docx import Document as create_docx_document
from docx.document import Document as DocxDocument
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor
from docx.text.paragraph import Paragraph
from docx.text.run import Run

from app.core.config import Settings
from app.core.logging import get_logger
from app.rendering.content import content_from_writing
from app.rendering.errors import DocumentRenderError, DocumentStorageError
from app.rendering.template import PROFESSIONAL_TEMPLATE, DocumentTemplate, resolve_template
from app.schemas.document import (
    BulletListBlock,
    DocumentContent,
    DocumentSection,
    HeadingBlock,
    PageBreakBlock,
    ParagraphBlock,
    RenderedDocument,
    TableBlock,
)
from app.schemas.writing import WritingResult

logger = get_logger(__name__)

PAGE_TOKEN = "{page}"
TOTAL_TOKEN = "{total}"
_PAGE_TOKEN_RE = re.compile(r"(\{page\}|\{total\})")
_UNSAFE_FILENAME_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')


class DocxRenderer:
    """Render structured content into a formatted DOCX stored on disk."""

    def __init__(
        self,
        *,
        output_dir: str | Path,
        template: DocumentTemplate | None = None,
    ) -> None:
        self._output_dir = Path(output_dir).expanduser()
        self._template = template or PROFESSIONAL_TEMPLATE

    @classmethod
    def from_settings(cls, settings: Settings) -> DocxRenderer:
        """Build a renderer from configured storage and template settings."""

        return cls(
            output_dir=settings.document_storage_dir,
            template=resolve_template(
                name=settings.document_template_name,
                path=settings.document_template_path or None,
            ),
        )

    @property
    def template(self) -> DocumentTemplate:
        return self._template

    def render(
        self,
        content: DocumentContent | WritingResult,
        *,
        output_name: str | None = None,
        overwrite: bool = True,
    ) -> RenderedDocument:
        """Render content, save it atomically, and return path plus metadata."""

        document_content = (
            content_from_writing(content) if isinstance(content, WritingResult) else content
        )
        rendered_at = datetime.now(UTC)
        document = self._build_document(document_content, rendered_at)
        path = self._store(document, document_content, output_name=output_name, overwrite=overwrite)
        content_hash = _sha256(path)
        byte_size = path.stat().st_size
        table_count = _count_tables(document_content)
        page_break_count = _count_page_breaks(document_content, self._template)
        source_ids = [source.citation_id for source in document_content.sources]

        metadata: dict[str, Any] = {
            **document_content.metadata,
            "title": document_content.title,
            "subtitle": document_content.subtitle,
            "template": self._template.name,
            "filename": path.name,
            "storage_path": str(path),
            "content_hash": content_hash,
            "byte_size": byte_size,
            "section_count": len(document_content.sections),
            "source_count": len(document_content.sources),
            "source_ids": source_ids,
            "table_count": table_count,
            "page_break_count": page_break_count,
            "rendered_at": rendered_at.isoformat(),
        }
        logger.info(
            "document_rendered",
            extra={
                "path": str(path),
                "title": document_content.title,
                "template": self._template.name,
                "byte_size": byte_size,
                "table_count": table_count,
                "source_count": len(document_content.sources),
            },
        )
        return RenderedDocument(
            path=path,
            filename=path.name,
            title=document_content.title,
            content_hash=content_hash,
            byte_size=byte_size,
            section_count=len(document_content.sections),
            source_count=len(document_content.sources),
            table_count=table_count,
            page_break_count=page_break_count,
            template_name=self._template.name,
            rendered_at=rendered_at,
            metadata=metadata,
        )

    def _build_document(
        self,
        content: DocumentContent,
        rendered_at: datetime,
    ) -> DocxDocument:
        document = self._load_base_document()
        self._configure_styles(document)
        self._configure_core_properties(document, content, rendered_at)

        for page_section in document.sections:
            self._configure_page(page_section)

        if self._template.title_page:
            self._add_title_page(document, content)
            self._add_page_break(document)
        else:
            self._add_document_title(document, content)

        for content_section in content.sections:
            if content_section.page_break_before:
                self._add_page_break(document)
            self._add_section(document, content_section)

        if content.include_sources and content.sources and self._template.source_heading.strip():
            self._add_sources(document, content)

        for page_section in document.sections:
            self._configure_header_and_footer(page_section, content)
        return document

    def _load_base_document(self) -> DocxDocument:
        path = self._template.path
        if path is None:
            return create_docx_document()
        try:
            document = create_docx_document(str(path))
        except Exception as exc:
            raise DocumentRenderError(f"Unable to load DOCX template {path}: {exc}") from exc
        if self._template.clear_template_body:
            self._clear_body(document)
        return document

    @staticmethod
    def _clear_body(document: DocxDocument) -> None:
        body = document.element.body
        for child in list(body.iterchildren()):
            if child.tag != qn("w:sectPr"):
                body.remove(child)

    def _configure_styles(self, document: DocxDocument) -> None:
        normal = _style(document, "Normal")
        if normal is not None:
            _set_style_font(normal, self._template.font_name, self._template.body_font_size)
            normal.paragraph_format.space_after = Pt(6)
            normal.paragraph_format.line_spacing = 1.15
            normal.paragraph_format.widow_control = True

        title = _style(document, "Title")
        if title is not None:
            _set_style_font(
                title,
                self._template.heading_font_name,
                self._template.title_font_size,
                bold=True,
                color=self._template.title_color,
            )
            title.paragraph_format.space_after = Pt(18)
            title.paragraph_format.keep_with_next = True

        subtitle = _style(document, "Subtitle")
        if subtitle is not None:
            _set_style_font(
                subtitle,
                self._template.font_name,
                self._template.subtitle_font_size,
                italic=True,
                color=self._template.muted_color,
            )
            subtitle.paragraph_format.space_after = Pt(24)

        for level in range(1, 5):
            style = _style(document, f"Heading {level}")
            if style is None:
                continue
            _set_style_font(
                style,
                self._template.heading_font_name,
                self._template.heading_font_sizes[level - 1],
                bold=True,
                color=self._template.heading_color,
            )
            style.paragraph_format.keep_with_next = True
            style.paragraph_format.space_before = Pt(18 if level == 1 else 12)
            style.paragraph_format.space_after = Pt(8 if level == 1 else 6)

        caption = _style(document, "Caption")
        if caption is not None:
            _set_style_font(
                caption,
                self._template.font_name,
                9.0,
                italic=True,
                color=self._template.muted_color,
            )

    def _configure_core_properties(
        self,
        document: DocxDocument,
        content: DocumentContent,
        rendered_at: datetime,
    ) -> None:
        properties = document.core_properties
        properties.title = content.title
        properties.subject = content.subtitle or "Proposal"
        properties.author = content.prepared_by or "Proposal Research Agent"
        properties.last_modified_by = "Proposal Research Agent"
        properties.category = "Proposal"
        properties.comments = "Generated by the Proposal Research Agent"
        properties.keywords = "; ".join(source.citation_id for source in content.sources)
        properties.created = rendered_at
        properties.modified = rendered_at

    def _configure_page(self, section: Any) -> None:
        section.top_margin = Inches(self._template.margin_top_inches)
        section.bottom_margin = Inches(self._template.margin_bottom_inches)
        section.left_margin = Inches(self._template.margin_left_inches)
        section.right_margin = Inches(self._template.margin_right_inches)
        section.header_distance = Inches(self._template.header_distance_inches)
        section.footer_distance = Inches(self._template.footer_distance_inches)
        section.different_first_page_header_footer = bool(
            self._template.title_page and self._template.different_first_page_header_footer
        )

    def _add_document_title(self, document: DocxDocument, content: DocumentContent) -> None:
        title = document.add_paragraph(style="Title")
        title.paragraph_format.space_before = Pt(0)
        title_run = title.add_run(content.title)
        _set_run_font(
            title_run,
            self._template.heading_font_name,
            self._template.title_font_size,
            bold=True,
            color=self._template.title_color,
        )
        _add_bottom_border(title, self._template.accent_color, size=8, space=6)
        if content.subtitle:
            subtitle = document.add_paragraph(content.subtitle, style="Subtitle")
            _set_paragraph_font(
                subtitle,
                self._template.font_name,
                self._template.subtitle_font_size,
                italic=True,
                color=self._template.muted_color,
            )

    def _add_title_page(self, document: DocxDocument, content: DocumentContent) -> None:
        title = document.add_paragraph(style="Title")
        title.alignment = WD_ALIGN_PARAGRAPH.CENTER
        title.paragraph_format.space_before = Pt(120)
        title_run = title.add_run(content.title)
        _set_run_font(
            title_run,
            self._template.heading_font_name,
            self._template.title_font_size,
            bold=True,
            color=self._template.title_color,
        )
        _add_bottom_border(title, self._template.accent_color, size=12, space=8)

        if content.subtitle:
            subtitle = document.add_paragraph(content.subtitle, style="Subtitle")
            subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER

        details = [
            ("Prepared for", content.prepared_for),
            ("Prepared by", content.prepared_by),
            ("Date", _format_date(content.document_date) if content.document_date else None),
        ]
        for key in self._template.title_page_metadata_keys:
            value = content.metadata.get(key)
            if value is not None:
                details.append((key.replace("_", " ").title(), str(value)))

        detail_lines = [(label, value) for label, value in details if value]
        if detail_lines:
            document.add_paragraph()
        for label, value in detail_lines:
            paragraph = document.add_paragraph()
            paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
            paragraph.paragraph_format.space_after = Pt(4)
            label_run = paragraph.add_run(f"{label}: ")
            label_run.bold = True
            label_run.font.color.rgb = RGBColor.from_string(self._template.heading_color)
            paragraph.add_run(value)

    def _add_section(self, document: DocxDocument, section: DocumentSection) -> None:
        heading = document.add_paragraph(style="Heading 1")
        heading.add_run(section.heading)
        _add_bottom_border(heading, self._template.accent_color, size=6, space=4)
        if section.subtitle:
            subtitle = document.add_paragraph(section.subtitle)
            subtitle.paragraph_format.space_after = Pt(10)
            _set_paragraph_font(
                subtitle,
                self._template.font_name,
                self._template.body_font_size,
                italic=True,
                color=self._template.muted_color,
            )

        for block in section.blocks:
            if isinstance(block, ParagraphBlock):
                self._add_paragraph(document, block.text)
            elif isinstance(block, HeadingBlock):
                self._add_heading(document, block)
            elif isinstance(block, BulletListBlock):
                self._add_bullets(document, block.items)
            elif isinstance(block, TableBlock):
                self._add_table(document, block)
            elif isinstance(block, PageBreakBlock):
                self._add_page_break(document)

    def _add_paragraph(self, document: DocxDocument, text: str) -> None:
        paragraph = document.add_paragraph(style="Normal")
        paragraph.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        paragraph.add_run(text)

    def _add_heading(self, document: DocxDocument, block: HeadingBlock) -> None:
        paragraph = document.add_paragraph(style=f"Heading {block.level}")
        paragraph.add_run(block.text)

    def _add_bullets(self, document: DocxDocument, items: list[str]) -> None:
        for item in items:
            paragraph = self._new_bullet_paragraph(document)
            paragraph.add_run(item)
            paragraph.paragraph_format.space_after = Pt(3)

    def _new_bullet_paragraph(self, document: DocxDocument) -> Paragraph:
        try:
            return document.add_paragraph(style=self._template.bullet_style)
        except KeyError:
            paragraph = document.add_paragraph(style="Normal")
            paragraph.paragraph_format.left_indent = Inches(0.25)
            paragraph.add_run("• ")
            return paragraph

    def _add_table(self, document: DocxDocument, block: TableBlock) -> None:
        if block.caption:
            caption = document.add_paragraph(block.caption, style="Caption")
            caption.paragraph_format.keep_with_next = True

        column_count = len(block.headers) if block.headers is not None else len(block.rows[0])
        row_count = len(block.rows) + (1 if block.headers is not None else 0)
        table = document.add_table(rows=row_count, cols=column_count)
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        table.autofit = True
        try:
            table.style = self._template.table_style
        except KeyError:
            table.style = "Table Grid"

        row_index = 0
        if block.headers is not None:
            header_row = table.rows[0]
            for column_index, text in enumerate(block.headers):
                self._fill_table_cell(
                    header_row.cells[column_index],
                    text,
                    header=True,
                )
            _repeat_table_header(header_row)
            row_index = 1

        for data_row in block.rows:
            for column_index, text in enumerate(data_row):
                self._fill_table_cell(
                    table.rows[row_index].cells[column_index],
                    text,
                    header=False,
                )
            _prevent_row_split(table.rows[row_index])
            row_index += 1

        document.add_paragraph().paragraph_format.space_after = Pt(2)

    def _fill_table_cell(self, cell: Any, text: str, *, header: bool) -> None:
        cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
        paragraph = cell.paragraphs[0]
        paragraph.paragraph_format.space_after = Pt(2)
        run = paragraph.add_run(text)
        _set_run_font(
            run,
            self._template.font_name,
            9.5,
            bold=header,
            color=self._template.table_header_text_color if header else None,
        )
        if header:
            _shade_cell(cell, self._template.accent_color)

    def _add_sources(self, document: DocxDocument, content: DocumentContent) -> None:
        heading = document.add_paragraph(style="Heading 1")
        heading.add_run(self._template.source_heading)
        _add_bottom_border(heading, self._template.accent_color, size=6, space=4)
        for source in content.sources:
            paragraph = self._new_bullet_paragraph(document)
            citation = paragraph.add_run(f"[{source.citation_id}] ")
            citation.bold = True
            paragraph.add_run(source.source_name)
            if source.chunk_index is not None:
                paragraph.add_run(f", chunk {source.chunk_index}")
            document_id = paragraph.add_run(f" ({source.document_id})")
            document_id.font.color.rgb = RGBColor.from_string(self._template.muted_color)
            paragraph.paragraph_format.space_after = Pt(3)

    def _add_page_break(self, document: DocxDocument) -> None:
        document.add_page_break()  # type: ignore[no-untyped-call]

    def _configure_header_and_footer(
        self,
        section: Any,
        content: DocumentContent,
    ) -> None:
        if self._template.header_text is not None:
            header = section.header
            header.is_linked_to_previous = False
            paragraph = header.paragraphs[0]
            _clear_paragraph(paragraph)
            paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
            text = _render_template_text(self._template.header_text, content)
            if text:
                run = paragraph.add_run(text)
                _set_run_font(
                    run,
                    self._template.font_name,
                    9.0,
                    italic=True,
                    color=self._template.muted_color,
                )
                _add_bottom_border(paragraph, self._template.accent_color, size=4, space=2)

        if self._template.footer_text is not None or self._template.include_page_numbers:
            footer = section.footer
            footer.is_linked_to_previous = False
            paragraph = footer.paragraphs[0]
            _clear_paragraph(paragraph)
            paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER

            wrote_content = False
            if self._template.footer_text is not None:
                footer_text = _render_template_text(self._template.footer_text, content)
                if footer_text:
                    paragraph.add_run(footer_text)
                    wrote_content = True
            if self._template.include_page_numbers:
                if wrote_content:
                    paragraph.add_run("  |  ")
                self._add_page_number_field(paragraph)
            if wrote_content or self._template.include_page_numbers:
                for run in paragraph.runs:
                    _set_run_font(
                        run,
                        self._template.font_name,
                        9.0,
                        color=self._template.muted_color,
                    )

        if section.different_first_page_header_footer:
            first_header = section.first_page_header
            first_header.is_linked_to_previous = False
            for paragraph in first_header.paragraphs:
                _clear_paragraph(paragraph)
            first_footer = section.first_page_footer
            first_footer.is_linked_to_previous = False
            for paragraph in first_footer.paragraphs:
                _clear_paragraph(paragraph)

    def _add_page_number_field(self, paragraph: Paragraph) -> None:
        page_format = self._template.page_number_format or "Page {page} of {total}"
        for part in _PAGE_TOKEN_RE.split(page_format):
            if part == PAGE_TOKEN:
                _add_field(paragraph, "PAGE")
            elif part == TOTAL_TOKEN:
                _add_field(paragraph, "NUMPAGES")
            elif part:
                paragraph.add_run(part)

    def _store(
        self,
        document: DocxDocument,
        content: DocumentContent,
        *,
        output_name: str | None,
        overwrite: bool,
    ) -> Path:
        try:
            self._output_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise DocumentStorageError(
                f"Unable to create document storage directory {self._output_dir}: {exc}"
            ) from exc

        filename = _resolve_filename(
            output_name=output_name,
            title=content.title,
            timestamp=datetime.now(UTC),
        )
        target = (self._output_dir / filename).resolve()
        if not target.is_relative_to(self._output_dir.resolve()):
            raise DocumentStorageError("Resolved document path escapes the storage directory")
        if target.exists() and not overwrite:
            raise DocumentStorageError(f"Document already exists: {target}")

        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".docx-",
            suffix=".tmp",
            dir=self._output_dir,
        )
        os.close(descriptor)
        temporary_path = Path(temporary_name)
        try:
            document.save(str(temporary_path))
            os.replace(temporary_path, target)
        except Exception as exc:
            raise DocumentStorageError(f"Unable to save DOCX document {target}: {exc}") from exc
        finally:
            temporary_path.unlink(missing_ok=True)
        return target


def _style(document: DocxDocument, name: str) -> Any:
    try:
        return document.styles[name]
    except KeyError:
        return None


def _set_style_font(
    style: Any,
    name: str,
    size: float,
    *,
    bold: bool = False,
    italic: bool = False,
    color: str | None = None,
) -> None:
    style.font.name = name
    style.font.size = Pt(size)
    style.font.bold = bold
    style.font.italic = italic
    if color is not None:
        style.font.color.rgb = RGBColor.from_string(color)


def _set_run_font(
    run: Run,
    name: str,
    size: float,
    *,
    bold: bool = False,
    italic: bool = False,
    color: str | None = None,
) -> None:
    run.font.name = name
    run.font.size = Pt(size)
    run.bold = bold
    run.italic = italic
    if color is not None:
        run.font.color.rgb = RGBColor.from_string(color)


def _set_paragraph_font(
    paragraph: Paragraph,
    name: str,
    size: float,
    *,
    italic: bool = False,
    color: str | None = None,
) -> None:
    for run in paragraph.runs:
        _set_run_font(run, name, size, italic=italic, color=color)


def _clear_paragraph(paragraph: Paragraph) -> None:
    paragraph.text = ""


def _add_bottom_border(
    paragraph: Paragraph,
    color: str,
    *,
    size: int,
    space: int,
) -> None:
    properties = paragraph._p.get_or_add_pPr()
    borders = properties.find(qn("w:pBdr"))
    if borders is None:
        borders = OxmlElement("w:pBdr")
        properties.append(borders)
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), str(size))
    bottom.set(qn("w:space"), str(space))
    bottom.set(qn("w:color"), color.removeprefix("#"))
    borders.append(bottom)


def _shade_cell(cell: Any, color: str) -> None:
    properties = cell._tc.get_or_add_tcPr()
    shading = OxmlElement("w:shd")
    shading.set(qn("w:val"), "clear")
    shading.set(qn("w:color"), "auto")
    shading.set(qn("w:fill"), color.removeprefix("#"))
    properties.append(shading)


def _repeat_table_header(row: Any) -> None:
    properties = row._tr.get_or_add_trPr()
    header = OxmlElement("w:tblHeader")
    header.set(qn("w:val"), "true")
    properties.append(header)


def _prevent_row_split(row: Any) -> None:
    properties = row._tr.get_or_add_trPr()
    no_split = OxmlElement("w:cantSplit")
    properties.append(no_split)


def _add_field(paragraph: Paragraph, instruction: str) -> None:
    _add_field_char(paragraph, "begin")
    instruction_run = paragraph.add_run()
    instruction_text = OxmlElement("w:instrText")
    instruction_text.set(qn("xml:space"), "preserve")
    instruction_text.text = instruction
    instruction_run._r.append(instruction_text)
    _add_field_char(paragraph, "separate")
    paragraph.add_run("1")
    _add_field_char(paragraph, "end")


def _add_field_char(paragraph: Paragraph, field_type: str) -> None:
    run = paragraph.add_run()
    field_char = OxmlElement("w:fldChar")
    field_char.set(qn("w:fldCharType"), field_type)
    run._r.append(field_char)


def _render_template_text(value: str, content: DocumentContent) -> str:
    document_date = content.document_date
    replacements = {
        "{title}": content.title,
        "{subtitle}": content.subtitle or "",
        "{prepared_for}": content.prepared_for or "",
        "{prepared_by}": content.prepared_by or "",
        "{date}": _format_date(document_date) if document_date else "",
    }
    rendered = value
    for token, replacement in replacements.items():
        rendered = rendered.replace(token, replacement)
    return rendered.strip()


def _format_date(value: date) -> str:
    return f"{value:%B} {value.day}, {value.year}"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise DocumentStorageError(f"Unable to hash rendered document {path}: {exc}") from exc
    return digest.hexdigest()


def _resolve_filename(*, output_name: str | None, title: str, timestamp: datetime) -> str:
    if output_name:
        raw_name = Path(output_name).name
        stem = Path(raw_name).stem or "document"
        suffix = ".docx"
    else:
        stem = _slugify(title) or "document"
        suffix = f"-{timestamp:%Y%m%dT%H%M%S%fZ}.docx"
    safe_stem = _UNSAFE_FILENAME_RE.sub("-", stem).strip(". ") or "document"
    return f"{safe_stem}{suffix}"


def _slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^A-Za-z0-9]+", "-", ascii_value).strip("-").lower()


def _count_tables(content: DocumentContent) -> int:
    return sum(
        1
        for section in content.sections
        for block in section.blocks
        if isinstance(block, TableBlock)
    )


def _count_page_breaks(content: DocumentContent, template: DocumentTemplate) -> int:
    explicit = sum(
        1
        for section in content.sections
        for block in section.blocks
        if isinstance(block, PageBreakBlock)
    )
    section_breaks = sum(1 for section in content.sections if section.page_break_before)
    return explicit + section_breaks + (1 if template.title_page else 0)


__all__ = ["DocxRenderer"]
