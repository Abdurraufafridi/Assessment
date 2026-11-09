"""Document loading and text extraction."""

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from docx import Document as DocxDocument
from pypdf import PdfReader

from app.ingestion.errors import DocumentExtractionError, UnsupportedDocumentTypeError


@dataclass(frozen=True, slots=True)
class ExtractedDocument:
    """Raw text and basic structure extracted from a source document."""

    text: str
    file_type: str
    page_count: int | None = None


class DocumentLoader(Protocol):
    """Interface implemented by format-specific document loaders."""

    extensions: frozenset[str]

    def load(self, path: Path) -> ExtractedDocument:
        """Extract text from ``path`` or raise :class:`DocumentExtractionError`."""


class TextLoader:
    """Loader for UTF-8 text and Markdown files."""

    extensions = frozenset({".txt", ".md", ".markdown"})

    def load(self, path: Path) -> ExtractedDocument:
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise DocumentExtractionError(f"{path.name} is not valid UTF-8 text") from exc
        except OSError as exc:
            raise DocumentExtractionError(f"Unable to read {path.name}: {exc}") from exc
        return ExtractedDocument(text=text, file_type=path.suffix.lstrip(".").lower())


class PdfLoader:
    """Loader for text-based PDF documents."""

    extensions = frozenset({".pdf"})

    def load(self, path: Path) -> ExtractedDocument:
        try:
            with path.open("rb") as stream:
                reader = PdfReader(stream)
                if reader.is_encrypted:
                    raise DocumentExtractionError(f"{path.name} is password-protected")
                page_text = [page.extract_text() or "" for page in reader.pages]
        except DocumentExtractionError:
            raise
        except Exception as exc:
            raise DocumentExtractionError(f"Unable to parse PDF {path.name}: {exc}") from exc

        return ExtractedDocument(
            text="\n\n".join(page_text),
            file_type="pdf",
            page_count=len(page_text),
        )


class DocxLoader:
    """Loader for Word (``.docx``) documents, including table cells."""

    extensions = frozenset({".docx"})

    def load(self, path: Path) -> ExtractedDocument:
        try:
            document = DocxDocument(str(path))
        except Exception as exc:
            raise DocumentExtractionError(f"Unable to parse DOCX {path.name}: {exc}") from exc

        parts = [paragraph.text for paragraph in document.paragraphs if paragraph.text.strip()]
        for table in document.tables:
            for row in table.rows:
                cells = [cell.text.strip() for cell in row.cells]
                row_text = " | ".join(cell for cell in cells if cell)
                if row_text:
                    parts.append(row_text)

        return ExtractedDocument(text="\n\n".join(parts), file_type="docx")


class DocumentLoaderRegistry:
    """Dispatches files to the loader registered for their extension."""

    def __init__(self, loaders: list[DocumentLoader] | None = None) -> None:
        self._loaders = loaders or [TextLoader(), PdfLoader(), DocxLoader()]
        self._by_extension: dict[str, DocumentLoader] = {}
        for loader in self._loaders:
            for extension in loader.extensions:
                self._by_extension[extension.lower()] = loader

    @property
    def supported_extensions(self) -> frozenset[str]:
        return frozenset(self._by_extension)

    def load(self, path: Path) -> ExtractedDocument:
        extension = path.suffix.lower()
        loader = self._by_extension.get(extension)
        if loader is None:
            supported = ", ".join(sorted(self._by_extension))
            raise UnsupportedDocumentTypeError(
                f"Unsupported document type '{extension}' for {path.name}; supported: {supported}"
            )
        return loader.load(path)
