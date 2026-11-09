"""Unit tests for document loaders."""

from pathlib import Path

import pytest
from docx import Document as DocxDocument

from app.ingestion.errors import DocumentExtractionError, UnsupportedDocumentTypeError
from app.ingestion.loaders import DocumentLoaderRegistry

pytestmark = pytest.mark.unit


def _write_minimal_pdf(path: Path, text: str) -> None:
    """Create a tiny text PDF without adding a PDF-generation dependency."""

    content = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>"
        ),
        f"<< /Length {len(content)} >>\nstream\n".encode() + content + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]

    output = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, obj in enumerate(objects, start=1):
        offsets.append(len(output))
        output.extend(f"{number} 0 obj\n".encode())
        output.extend(obj)
        output.extend(b"\nendobj\n")

    xref_offset = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n".encode())
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode())
    output.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode()
    )
    path.write_bytes(output)


def test_text_loader_extracts_utf8(tmp_path: Path) -> None:
    path = tmp_path / "sample.txt"
    path.write_text("Client discovery notes\nBudget: $50,000", encoding="utf-8")

    document = DocumentLoaderRegistry().load(path)

    assert document.file_type == "txt"
    assert "Budget: $50,000" in document.text


def test_markdown_loader_uses_text_loader(tmp_path: Path) -> None:
    path = tmp_path / "notes.md"
    path.write_text("# Heading\n\nBody", encoding="utf-8")

    document = DocumentLoaderRegistry().load(path)

    assert document.file_type == "md"
    assert "# Heading" in document.text


def test_pdf_loader_extracts_text_and_page_count(tmp_path: Path) -> None:
    path = tmp_path / "sample.pdf"
    _write_minimal_pdf(path, "Warehouse inventory visibility")

    document = DocumentLoaderRegistry().load(path)

    assert document.file_type == "pdf"
    assert document.page_count == 1
    assert "Warehouse inventory visibility" in document.text


def test_docx_loader_extracts_paragraphs_and_tables(tmp_path: Path) -> None:
    path = tmp_path / "sample.docx"
    word_document = DocxDocument()
    word_document.add_paragraph("Executive summary")
    word_document.add_paragraph("Client needs inventory visibility.")
    table = word_document.add_table(rows=1, cols=2)
    table.rows[0].cells[0].text = "Budget"
    table.rows[0].cells[1].text = "$50,000"
    word_document.save(path)

    document = DocumentLoaderRegistry().load(path)

    assert document.file_type == "docx"
    assert "Client needs inventory visibility." in document.text
    assert "Budget | $50,000" in document.text


def test_unsupported_extension_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "sample.csv"
    path.write_text("a,b", encoding="utf-8")

    with pytest.raises(UnsupportedDocumentTypeError, match="Unsupported document type"):
        DocumentLoaderRegistry().load(path)


def test_invalid_text_encoding_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "sample.txt"
    path.write_bytes(b"\xff\xfe\x00\x00")

    with pytest.raises(DocumentExtractionError, match="not valid UTF-8"):
        DocumentLoaderRegistry().load(path)
