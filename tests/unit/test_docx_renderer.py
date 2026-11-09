"""Unit tests for Phase 5 DOCX rendering, formatting, and storage."""

import hashlib
from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest
from docx import Document as DocxDocument
from pydantic import ValidationError

from app.core.config import Settings
from app.rendering import DocumentTemplate, DocxRenderer, content_from_writing
from app.rendering.errors import DocumentStorageError, DocumentTemplateError
from app.rendering.parser import blocks_from_text
from app.rendering.template import get_template, resolve_template
from app.schemas.document import (
    BulletListBlock,
    DocumentContent,
    DocumentSection,
    HeadingBlock,
    PageBreakBlock,
    ParagraphBlock,
    TableBlock,
)
from app.schemas.writing import WritingResult, WritingSection
from tests.unit.phase4_helpers import make_source

pytestmark = pytest.mark.unit


def _style_name(paragraph: object) -> str:
    style = getattr(paragraph, "style", None)
    return getattr(style, "name", "") or ""


def _sample_content() -> DocumentContent:
    return DocumentContent(
        title="Acme Warehouse Modernization Proposal",
        subtitle="Technical response for operations leadership",
        prepared_for="Acme Operations",
        prepared_by="Proposal Team",
        document_date=date(2026, 11, 9),
        metadata={"version": "1.0", "client": "Acme", "industry": "logistics"},
        sections=[
            DocumentSection(
                heading="Client Needs",
                blocks=[
                    ParagraphBlock(
                        text=(
                            "Café & <special> “quotes” — 100% safe; 日本語 text "
                            "must remain intact [S1]."
                        )
                    ),
                    BulletListBlock(
                        items=[
                            "Real-time inventory visibility",
                            "Phased warehouse rollout",
                        ]
                    ),
                    HeadingBlock(level=2, text="Supporting Detail"),
                    TableBlock(
                        caption="Table 1: Delivery phases",
                        headers=["Phase", "Owner", "Timing"],
                        rows=[
                            ["Discovery", "Operations", "Q1"],
                            ["Rollout", "Delivery", "Q2"],
                        ],
                    ),
                    PageBreakBlock(),
                ],
            ),
            DocumentSection(heading="Empty Appendix"),
        ],
        sources=[make_source("S1", source_name="discovery_transcript.txt")],
    )


def test_renders_formatted_document_with_metadata_and_sources(tmp_path: Path) -> None:
    renderer = DocxRenderer(output_dir=tmp_path / "generated")

    result = renderer.render(_sample_content(), output_name="proposal.docx")

    assert result.path == (tmp_path / "generated" / "proposal.docx").resolve()
    assert result.path.is_file()
    assert result.filename == "proposal.docx"
    assert result.title == "Acme Warehouse Modernization Proposal"
    assert result.byte_size == result.path.stat().st_size
    assert result.content_hash == hashlib.sha256(result.path.read_bytes()).hexdigest()
    assert result.section_count == 2
    assert result.source_count == 1
    assert result.table_count == 1
    assert result.page_break_count == 2
    assert result.template_name == "professional"
    assert result.metadata["source_ids"] == ["S1"]
    assert result.metadata["client"] == "Acme"
    assert result.metadata["storage_path"] == str(result.path)

    document = DocxDocument(str(result.path))
    paragraph_text = [paragraph.text for paragraph in document.paragraphs]

    assert "Acme Warehouse Modernization Proposal" in paragraph_text
    assert "Technical response for operations leadership" in paragraph_text
    assert "Prepared for: Acme Operations" in paragraph_text
    assert "Date: November 9, 2026" in paragraph_text
    assert "Client Needs" in paragraph_text
    assert "Empty Appendix" in paragraph_text
    assert any("Café & <special>" in text and "日本語" in text for text in paragraph_text)
    assert any("[S1]" in text for text in paragraph_text)
    assert any("[S1] discovery_transcript.txt" in text for text in paragraph_text)

    headings = {paragraph.text: _style_name(paragraph) for paragraph in document.paragraphs}
    assert headings["Client Needs"] == "Heading 1"
    assert headings["Supporting Detail"] == "Heading 2"

    bullets = [
        paragraph for paragraph in document.paragraphs if _style_name(paragraph) == "List Bullet"
    ]
    assert [paragraph.text for paragraph in bullets[:2]] == [
        "Real-time inventory visibility",
        "Phased warehouse rollout",
    ]

    assert len(document.tables) == 1
    table = document.tables[0]
    assert table.cell(0, 0).text == "Phase"
    assert table.cell(1, 0).text == "Discovery"
    assert (
        table.cell(0, 0)
        ._tc.xpath(".//w:shd")[0]
        .get("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}fill")
        == "2F5597"
    )

    page_breaks = document.element.body.xpath('.//w:br[@w:type="page"]')
    assert len(page_breaks) == 2

    section = document.sections[0]
    assert section.header.paragraphs[0].text == "Acme Warehouse Modernization Proposal"
    assert "Confidential" in section.footer.paragraphs[0].text
    field_instructions = [
        element.text for element in section.footer.paragraphs[0]._p.xpath(".//w:instrText")
    ]
    assert field_instructions == ["PAGE", "NUMPAGES"]
    assert section.first_page_header.paragraphs[0].text == ""
    assert section.first_page_footer.paragraphs[0].text == ""
    top_margin = section.top_margin
    assert top_margin is not None
    assert top_margin.inches == pytest.approx(0.9)

    properties = document.core_properties
    assert properties.title == "Acme Warehouse Modernization Proposal"
    assert properties.author == "Proposal Team"
    assert properties.keywords == "S1"


def test_empty_sections_and_empty_documents_render_without_error(tmp_path: Path) -> None:
    renderer = DocxRenderer(
        output_dir=tmp_path,
        template=get_template("minimal"),
    )

    empty_section_result = renderer.render(
        DocumentContent(
            title="Empty Section Test",
            sections=[DocumentSection(heading="Appendix")],
        ),
        output_name="empty-section.docx",
    )
    empty_document_result = renderer.render(
        DocumentContent(title="No Sections"),
        output_name="no-sections.docx",
    )

    empty_section = DocxDocument(str(empty_section_result.path))
    empty_document = DocxDocument(str(empty_document_result.path))

    assert "Appendix" in [paragraph.text for paragraph in empty_section.paragraphs]
    assert empty_section.tables == []
    assert "No Sections" in [paragraph.text for paragraph in empty_document.paragraphs]
    assert empty_document.tables == []


def test_writing_result_conversion_parses_bullets_tables_and_page_break(tmp_path: Path) -> None:
    source = make_source("S1", source_name="research_notes.txt")
    writing = WritingResult(
        title="Converted Writing Result",
        sections=[
            WritingSection(
                heading="Findings",
                content=(
                    "Supported paragraph with a citation [S1].\n\n"
                    "- First finding\n"
                    "- Second finding\n\n"
                    "### Delivery Detail\n\n"
                    "| Item | Owner |\n"
                    "| --- | --- |\n"
                    "| Portal | Operations |\n\n"
                    "<!-- pagebreak -->"
                ),
                citation_ids=["S1"],
            )
        ],
        sources=[source],
    )
    content = content_from_writing(writing)
    renderer = DocxRenderer(
        output_dir=tmp_path,
        template=DocumentTemplate(
            name="compact",
            title_page=False,
            header_text=None,
            footer_text=None,
            include_page_numbers=False,
        ),
    )

    result = renderer.render(writing, output_name="converted.docx")
    document = DocxDocument(str(result.path))

    assert content.sections[0].heading == "Findings"
    assert isinstance(content.sections[0].blocks[1], BulletListBlock)
    assert isinstance(content.sections[0].blocks[3], TableBlock)
    assert isinstance(content.sections[0].blocks[4], PageBreakBlock)
    assert document.tables[0].cell(1, 0).text == "Portal"
    bullets = [
        paragraph.text
        for paragraph in document.paragraphs
        if _style_name(paragraph) == "List Bullet"
    ]
    assert bullets[:2] == ["First finding", "Second finding"]
    assert {paragraph.text: _style_name(paragraph) for paragraph in document.paragraphs}[
        "Delivery Detail"
    ] == "Heading 3"
    assert len(document.element.body.xpath('.//w:br[@w:type="page"]')) == 1


def test_custom_template_configuration_controls_formatting(tmp_path: Path) -> None:
    template = DocumentTemplate(
        name="custom",
        font_name="Georgia",
        heading_font_name="Georgia",
        body_font_size=11.0,
        title_color="333333",
        heading_color="333333",
        accent_color="808080",
        title_page=False,
        header_text="Acme Confidential",
        footer_text="{title} | {date}",
        include_page_numbers=False,
    )
    renderer = DocxRenderer(output_dir=tmp_path, template=template)
    content = DocumentContent(
        title="Configured Template",
        document_date=date(2026, 1, 2),
        sections=[DocumentSection(heading="Overview", blocks=[ParagraphBlock(text="Body.")])],
    )

    result = renderer.render(content, output_name="custom.docx")
    document = DocxDocument(str(result.path))

    assert result.template_name == "custom"
    assert document.styles["Normal"].font.name == "Georgia"
    assert document.styles["Heading 1"].font.name == "Georgia"
    assert document.sections[0].header.paragraphs[0].text == "Acme Confidential"
    assert document.sections[0].footer.paragraphs[0].text == "Configured Template | January 2, 2026"
    assert not document.sections[0].footer.paragraphs[0]._p.xpath(".//w:instrText")
    assert "Prepared for" not in [paragraph.text for paragraph in document.paragraphs]


def test_base_docx_template_is_loaded_and_placeholder_body_is_cleared(tmp_path: Path) -> None:
    base_path = tmp_path / "base.docx"
    base = DocxDocument()
    base.sections[0].header.paragraphs[0].text = "Base Template Header"
    base.add_paragraph("Template placeholder body")
    base.save(str(base_path))

    base_template = resolve_template(name="brand", path=base_path)
    assert base_template.path == base_path.resolve()
    template = replace(
        base_template,
        header_text=None,
        footer_text=None,
        include_page_numbers=False,
    )
    renderer = DocxRenderer(output_dir=tmp_path / "output", template=template)

    result = renderer.render(
        DocumentContent(
            title="From Base Template",
            sections=[DocumentSection(heading="Body")],
        ),
        output_name="from-base.docx",
    )
    document = DocxDocument(str(result.path))

    assert result.template_name == "brand"
    assert "Template placeholder body" not in [paragraph.text for paragraph in document.paragraphs]
    assert document.sections[0].header.paragraphs[0].text == "Base Template Header"
    assert "From Base Template" in [paragraph.text for paragraph in document.paragraphs]


def test_storage_overwrite_and_template_errors(tmp_path: Path) -> None:
    renderer = DocxRenderer(output_dir=tmp_path)
    content = DocumentContent(title="Storage")

    first = renderer.render(content, output_name="same.docx")
    assert first.path.is_file()

    with pytest.raises(DocumentStorageError, match="already exists"):
        renderer.render(content, output_name="same.docx", overwrite=False)

    replaced = renderer.render(content, output_name="same.docx")
    assert replaced.path == first.path

    with pytest.raises(DocumentTemplateError, match="does not exist"):
        resolve_template(name="brand", path=tmp_path / "missing.docx")
    with pytest.raises(DocumentTemplateError, match="Unknown"):
        resolve_template(name="unknown")


def test_from_settings_uses_configured_storage_and_template(tmp_path: Path) -> None:
    settings = Settings(
        _env_file=None,
        app_env="test",
        document_storage_dir=str(tmp_path / "configured"),
        document_template_name="minimal",
    )

    renderer = DocxRenderer.from_settings(settings)
    result = renderer.render(DocumentContent(title="Configured Storage"))

    assert result.path.parent == (tmp_path / "configured").resolve()
    assert result.path.is_file()
    assert result.template_name == "minimal"


def test_parser_handles_special_characters_and_ragged_table_text() -> None:
    blocks = blocks_from_text(
        "Text with & < > “quotes” and emoji 🚀.\n\n"
        "| A | B |\n"
        "| --- | --- |\n"
        "| one \\| two | three |"
    )

    assert blocks[0] == ParagraphBlock(text="Text with & < > “quotes” and emoji 🚀.")
    table = blocks[1]
    assert isinstance(table, TableBlock)
    assert table.headers == ["A", "B"]
    assert table.rows == [["one | two", "three"]]


def test_table_schema_rejects_ragged_rows() -> None:
    with pytest.raises(ValidationError, match="same number of cells"):
        TableBlock(headers=["A", "B"], rows=[["one"]])
