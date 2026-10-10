"""The one place where errors become HTTP responses.

Every error body has the same shape (see app.models.ErrorResponse), so a client
needs exactly one error-parsing code path.
"""

import logging
import math

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.errors import (
    IngestError,
    InvalidCursor,
    NotFound,
    ProviderError,
    RateLimited,
    SpecSeekError,
)
from app.logging_config import request_id_var

logger = logging.getLogger("specseek.errors")

# Domain error -> HTTP status. Looked up along the class hierarchy, so a subclass
# without its own entry inherits its parent's status.
_STATUS_BY_ERROR: dict[type[SpecSeekError], int] = {
    NotFound: 404,
    InvalidCursor: 422,
    IngestError: 422,  # the client's file is the problem
    RateLimited: 429,  # "Too Many Requests"
    ProviderError: 502,  # an upstream service we depend on failed ("Bad Gateway")
    SpecSeekError: 500,
}


_CODE_BY_HTTP_STATUS = {404: "not_found", 405: "method_not_allowed"}


def status_for(exc: SpecSeekError) -> int:
    for cls in type(exc).__mro__:
        if cls in _STATUS_BY_ERROR:
            return _STATUS_BY_ERROR[cls]
    return 500


def _error_body(code: str, message: str, details: object = None) -> dict[str, object]:
    error: dict[str, object] = {
        "code": code,
        "message": message,
        "request_id": request_id_var.get(),
    }
    if details is not None:
        error["details"] = details
    return {"error": error}


async def handle_specseek_error(request: Request, exc: SpecSeekError) -> JSONResponse:
    status_code = status_for(exc)
    # 5xx = our side failed: log as error. 4xx = the caller's mistake: a warning is enough.
    log = logger.error if status_code >= 500 else logger.warning
    log("domain_error", extra={"code": exc.code, "detail": exc.message, "status": status_code})
    headers = None
    if isinstance(exc, RateLimited):
        # The standard header for "wait this many seconds"; whole seconds, rounded up so a
        # client that obeys it is never early.
        headers = {"Retry-After": str(max(1, math.ceil(exc.retry_after_seconds)))}
    return JSONResponse(
        status_code=status_code, content=_error_body(exc.code, exc.message), headers=headers
    )


async def handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    # FastAPI raises this before the route runs when the request doesn't match the models.
    details = [
        {"field": ".".join(str(part) for part in err["loc"]), "problem": err["msg"]}
        for err in jsonable_encoder(exc.errors())
    ]
    return JSONResponse(
        status_code=422,
        content=_error_body("validation_error", "Request validation failed", details),
    )


async def handle_http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    # Raised by the framework itself: unknown path (404), wrong verb (405), ...
    code = _CODE_BY_HTTP_STATUS.get(exc.status_code, "http_error")
    return JSONResponse(
        status_code=exc.status_code,
        content=_error_body(code, str(exc.detail)),
        headers=exc.headers,  # e.g. 405 carries an `Allow` header listing the valid verbs
    )


def install_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(SpecSeekError, handle_specseek_error)
    app.add_exception_handler(RequestValidationError, handle_validation_error)
    app.add_exception_handler(StarletteHTTPException, handle_http_exception)
