"""Configurable visual templates for generated DOCX documents."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

from app.rendering.errors import DocumentTemplateError


@dataclass(frozen=True, slots=True)
class DocumentTemplate:
    """Formatting configuration and optional base DOCX template."""

    name: str = "professional"
    path: Path | None = None
    clear_template_body: bool = True

    font_name: str = "Calibri"
    heading_font_name: str = "Calibri Light"
    body_font_size: float = 10.5
    title_font_size: float = 28.0
    subtitle_font_size: float = 14.0
    heading_font_sizes: tuple[float, float, float, float] = (18.0, 14.0, 12.0, 11.0)

    title_color: str = "1F3864"
    heading_color: str = "1F3864"
    accent_color: str = "2F5597"
    muted_color: str = "595959"
    table_header_text_color: str = "FFFFFF"

    margin_top_inches: float = 0.9
    margin_bottom_inches: float = 0.9
    margin_left_inches: float = 1.0
    margin_right_inches: float = 1.0
    header_distance_inches: float = 0.45
    footer_distance_inches: float = 0.45

    title_page: bool = True
    different_first_page_header_footer: bool = True
    title_page_metadata_keys: tuple[str, ...] = ("version", "client", "industry")

    header_text: str | None = "{title}"
    footer_text: str | None = "Confidential"
    include_page_numbers: bool = True
    page_number_format: str = "Page {page} of {total}"

    table_style: str = "Table Grid"
    bullet_style: str = "List Bullet"
    source_heading: str = "Sources"

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("Template name must not be blank")
        if not self.font_name.strip() or not self.heading_font_name.strip():
            raise ValueError("Template font names must not be blank")
        for field_name in (
            "body_font_size",
            "title_font_size",
            "subtitle_font_size",
            "margin_top_inches",
            "margin_bottom_inches",
            "margin_left_inches",
            "margin_right_inches",
            "header_distance_inches",
            "footer_distance_inches",
        ):
            if getattr(self, field_name) <= 0:
                raise ValueError(f"{field_name} must be positive")
        if len(self.heading_font_sizes) != 4 or any(size <= 0 for size in self.heading_font_sizes):
            raise ValueError("heading_font_sizes must contain four positive sizes")
        for field_name in (
            "title_color",
            "heading_color",
            "accent_color",
            "muted_color",
            "table_header_text_color",
        ):
            _validate_hex_color(field_name, getattr(self, field_name))
        if self.path is not None and self.path.suffix.lower() != ".docx":
            raise ValueError("Document template path must use the .docx extension")


def _validate_hex_color(field_name: str, value: str) -> None:
    cleaned = value.removeprefix("#")
    if len(cleaned) != 6 or any(character not in "0123456789abcdefABCDEF" for character in cleaned):
        raise ValueError(f"{field_name} must be a six-digit hexadecimal colour")


PROFESSIONAL_TEMPLATE = DocumentTemplate()
MINIMAL_TEMPLATE = DocumentTemplate(
    name="minimal",
    font_name="Arial",
    heading_font_name="Arial",
    body_font_size=10.0,
    title_font_size=22.0,
    subtitle_font_size=12.0,
    heading_font_sizes=(15.0, 12.5, 11.0, 10.5),
    title_color="000000",
    heading_color="000000",
    accent_color="404040",
    muted_color="666666",
    table_header_text_color="FFFFFF",
    title_page=False,
    header_text=None,
    footer_text=None,
    include_page_numbers=True,
    page_number_format="{page} / {total}",
)

BUILTIN_TEMPLATES: dict[str, DocumentTemplate] = {
    PROFESSIONAL_TEMPLATE.name: PROFESSIONAL_TEMPLATE,
    MINIMAL_TEMPLATE.name: MINIMAL_TEMPLATE,
}


def get_template(name: str) -> DocumentTemplate:
    """Return a built-in template by name."""

    template = BUILTIN_TEMPLATES.get(name)
    if template is None:
        available = ", ".join(sorted(BUILTIN_TEMPLATES))
        raise DocumentTemplateError(
            f"Unknown document template '{name}'; available templates: {available}"
        )
    return template


def resolve_template(
    *,
    name: str = "professional",
    path: str | Path | None = None,
) -> DocumentTemplate:
    """Resolve a built-in template and optionally apply a base DOCX file."""

    base = BUILTIN_TEMPLATES.get(name)
    if base is None:
        if path is None:
            available = ", ".join(sorted(BUILTIN_TEMPLATES))
            raise DocumentTemplateError(
                f"Unknown document template '{name}'; available templates: {available}"
            )
        base = replace(DocumentTemplate(), name=name)

    resolved_path = Path(path).expanduser().resolve() if path is not None else None
    if resolved_path is not None:
        if not resolved_path.is_file():
            raise DocumentTemplateError(f"Document template does not exist: {resolved_path}")
        if resolved_path.suffix.lower() != ".docx":
            raise DocumentTemplateError("Document template path must use the .docx extension")
        base = replace(base, path=resolved_path)

    return base


__all__ = [
    "BUILTIN_TEMPLATES",
    "DocumentTemplate",
    "MINIMAL_TEMPLATE",
    "PROFESSIONAL_TEMPLATE",
    "get_template",
    "resolve_template",
]
