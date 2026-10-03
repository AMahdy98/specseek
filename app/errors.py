"""Domain exceptions. Raised by service/data code; they know nothing about HTTP.

The translation to status codes lives in exactly one place: app/api/error_handlers.py.
"""


class SpecSeekError(Exception):
    """Base class for every error we raise on purpose."""

    code = "internal_error"  # stable, machine-readable; clients branch on this, not on message

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message  # human-readable; safe to show to the client


class NotFound(SpecSeekError):
    """A requested resource (e.g. a document ID) does not exist."""

    code = "not_found"


class InvalidCursor(SpecSeekError):
    """The client sent a pagination cursor we did not issue (or tampered with one)."""

    code = "invalid_cursor"


class IngestError(SpecSeekError):
    """The submitted file can't be ingested (not a PDF, no extractable text, ...)."""

    code = "ingest_failed"


class ProviderError(SpecSeekError):
    """The embedding/LLM provider failed or timed out."""

    code = "provider_error"
