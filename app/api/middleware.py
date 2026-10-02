"""Request-context middleware: request ID, access log, last-resort error response.

Written as a plain ASGI middleware (an app that wraps another app) rather than
Starlette's BaseHTTPMiddleware: it runs in the same task as the route, so the
ContextVar set here is visible in every log line the request produces.
"""

import logging
import re
import time
import uuid

from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.logging_config import request_id_var

logger = logging.getLogger("specseek.access")

REQUEST_ID_HEADER = "X-Request-ID"
# Accept a caller's ID only if it's short and plain: it ends up in our logs, so we
# must not let a client inject newlines or megabytes of text.
_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":  # e.g. "lifespan" events: pass straight through
            await self.app(scope, receive, send)
            return

        incoming = Headers(scope=scope).get(REQUEST_ID_HEADER, "")
        request_id = incoming if _SAFE_REQUEST_ID.match(incoming) else uuid.uuid4().hex
        token = request_id_var.set(request_id)

        start = time.perf_counter()
        status_code = 500  # what we log if the app dies before sending a response
        response_started = False

        async def send_with_request_id(message: Message) -> None:
            nonlocal status_code, response_started
            if message["type"] == "http.response.start":
                response_started = True
                status_code = message["status"]
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        except Exception:
            # Anything no exception handler claimed: a bug. Log the stack trace, tell the
            # client nothing about internals except the ID to quote in a bug report.
            logger.exception("unhandled_exception")
            if response_started:
                raise  # headers already sent; too late to change the status code
            response = JSONResponse(
                status_code=500,
                content={
                    "error": {
                        "code": "internal_error",
                        "message": "Internal server error",
                        "request_id": request_id,
                    }
                },
            )
            await response(scope, receive, send_with_request_id)
        finally:
            logger.info(
                "request",
                extra={
                    "method": scope["method"],
                    "path": scope["path"],
                    "status": status_code,
                    "duration_ms": round((time.perf_counter() - start) * 1000, 2),
                },
            )
            request_id_var.reset(token)
