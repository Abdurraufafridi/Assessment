"""Document rendering, templates, and storage."""

from app.rendering.content import content_from_writing
from app.rendering.docx import DocxRenderer
from app.rendering.errors import DocumentRenderError, DocumentStorageError, DocumentTemplateError
from app.rendering.template import (
    BUILTIN_TEMPLATES,
    MINIMAL_TEMPLATE,
    PROFESSIONAL_TEMPLATE,
    DocumentTemplate,
    get_template,
    resolve_template,
)

__all__ = [
    "BUILTIN_TEMPLATES",
    "DocxRenderer",
    "DocumentRenderError",
    "DocumentStorageError",
    "DocumentTemplate",
    "DocumentTemplateError",
    "MINIMAL_TEMPLATE",
    "PROFESSIONAL_TEMPLATE",
    "content_from_writing",
    "get_template",
    "resolve_template",
]
