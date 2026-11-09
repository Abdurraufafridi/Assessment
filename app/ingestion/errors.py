"""Ingestion-specific exceptions."""


class IngestionError(Exception):
    """Base exception for recoverable ingestion failures."""


class UnsupportedDocumentTypeError(IngestionError):
    """Raised when no loader supports the supplied file extension."""


class DocumentExtractionError(IngestionError):
    """Raised when a supported document cannot be decoded or parsed."""


class DocumentTooLargeError(IngestionError):
    """Raised when a document exceeds the configured size limit."""


class EmptyDocumentError(IngestionError):
    """Raised when extraction or cleaning produces no usable text."""
