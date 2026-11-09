"""Errors raised while rendering and storing documents."""


class DocumentRenderError(Exception):
    """Base exception for document rendering failures."""


class DocumentTemplateError(DocumentRenderError):
    """Raised when a document template cannot be resolved or loaded."""


class DocumentStorageError(DocumentRenderError):
    """Raised when a rendered document cannot be stored safely."""


__all__ = ["DocumentRenderError", "DocumentStorageError", "DocumentTemplateError"]
