"""Structured logging: one JSON object per line on stdout.

Why JSON: log platforms (Cloud Logging, etc.) index the fields, so you can filter by
`request_id` or `status` instead of grepping free text.
"""

import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime

# Per-request value. A ContextVar is like thread-local storage, but per asyncio task:
# concurrent requests on the same thread each see their own value.
request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)

# Attributes every LogRecord has; anything else was passed via `extra={...}`.
_STANDARD_ATTRS = frozenset(vars(logging.LogRecord("", 0, "", 0, "", None, None))) | {
    "message",
    "asctime",
    "taskName",
    "color_message",  # uvicorn's ANSI-coloured duplicate of the message; noise in JSON
}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "severity": record.levelname,  # the field name Cloud Logging recognises
            "logger": record.name,
            "message": record.getMessage(),
        }
        request_id = request_id_var.get()
        if request_id is not None:
            payload["request_id"] = request_id
        # Fields passed as logger.info("...", extra={"status": 200}) become top-level keys.
        for key, value in vars(record).items():
            if key not in _STANDARD_ATTRS:
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        # default=str: never let an unserializable value crash logging itself.
        return json.dumps(payload, default=str)


def configure_logging(level: str) -> None:
    """Route all logs (ours and uvicorn's) through one JSON handler. Safe to call twice."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    handler.set_name("specseek-json")

    root = logging.getLogger()
    root.handlers[:] = [h for h in root.handlers if h.get_name() != "specseek-json"]
    root.addHandler(handler)
    root.setLevel(level.upper())

    # uvicorn installs its own plain-text handlers. Remove them so its messages
    # (startup, shutdown, errors) flow up to our JSON handler instead.
    for name in ("uvicorn", "uvicorn.error"):
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = True

    # We write our own access line (with request_id and duration) in the middleware,
    # so silence uvicorn's to avoid two lines per request.
    access_logger = logging.getLogger("uvicorn.access")
    access_logger.handlers.clear()
    access_logger.propagate = False
