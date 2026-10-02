"""Error envelope, request IDs and JSON logs.

Uses a tiny throwaway app with the *real* middleware and handlers installed, plus
routes that fail on purpose (the real API has no failing routes to borrow yet).
"""

import json
import logging

import httpx
import pytest
from fastapi import FastAPI
from pydantic import BaseModel

from app.api.error_handlers import install_error_handlers, status_for
from app.api.middleware import RequestContextMiddleware
from app.errors import IngestError, NotFound, ProviderError, SpecSeekError
from app.logging_config import JsonFormatter, request_id_var


class _Body(BaseModel):
    question: str


def _make_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestContextMiddleware)
    install_error_handlers(app)

    @app.get("/ok")
    async def ok() -> dict[str, str | None]:
        return {"seen_request_id": request_id_var.get()}

    @app.get("/missing")
    async def missing() -> None:
        raise NotFound("Document 'abc' not found")

    @app.get("/bug")
    async def bug() -> None:
        raise RuntimeError("secret internal detail")

    @app.post("/validated")
    async def validated(body: _Body) -> _Body:
        return body

    return app


@pytest.fixture
async def err_client():
    transport = httpx.ASGITransport(app=_make_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_generates_request_id_and_exposes_it_to_the_route(err_client):
    resp = await err_client.get("/ok")
    request_id = resp.headers["X-Request-ID"]
    assert len(request_id) == 32  # uuid4().hex
    assert resp.json() == {"seen_request_id": request_id}


async def test_reuses_a_safe_incoming_request_id(err_client):
    resp = await err_client.get("/ok", headers={"X-Request-ID": "trace-123"})
    assert resp.headers["X-Request-ID"] == "trace-123"


async def test_replaces_an_unsafe_incoming_request_id(err_client):
    resp = await err_client.get("/ok", headers={"X-Request-ID": "bad id with spaces!"})
    assert resp.headers["X-Request-ID"] != "bad id with spaces!"
    assert len(resp.headers["X-Request-ID"]) == 32


async def test_domain_error_becomes_error_envelope(err_client):
    resp = await err_client.get("/missing", headers={"X-Request-ID": "req-1"})
    assert resp.status_code == 404
    assert resp.json() == {
        "error": {
            "code": "not_found",
            "message": "Document 'abc' not found",
            "request_id": "req-1",
        }
    }


async def test_unhandled_exception_is_500_without_leaking_internals(err_client):
    resp = await err_client.get("/bug", headers={"X-Request-ID": "req-2"})
    assert resp.status_code == 500
    assert resp.headers["X-Request-ID"] == "req-2"
    assert resp.json() == {
        "error": {
            "code": "internal_error",
            "message": "Internal server error",
            "request_id": "req-2",
        }
    }
    assert "secret" not in resp.text


async def test_validation_error_uses_the_same_envelope(err_client):
    resp = await err_client.post("/validated", json={})
    assert resp.status_code == 422
    error = resp.json()["error"]
    assert error["code"] == "validation_error"
    assert error["details"] == [{"field": "body.question", "problem": "Field required"}]


async def test_framework_errors_use_the_same_envelope(err_client):
    unknown_path = await err_client.get("/nope")
    assert unknown_path.status_code == 404
    assert unknown_path.json()["error"]["code"] == "not_found"

    wrong_verb = await err_client.delete("/ok")
    assert wrong_verb.status_code == 405
    assert wrong_verb.json()["error"]["code"] == "method_not_allowed"
    assert wrong_verb.headers["Allow"] == "GET"


def test_status_mapping_follows_the_class_hierarchy():
    class PdfHasNoText(IngestError):  # a subclass with no entry of its own
        pass

    assert status_for(NotFound("x")) == 404
    assert status_for(IngestError("x")) == 422
    assert status_for(PdfHasNoText("x")) == 422
    assert status_for(ProviderError("x")) == 502
    assert status_for(SpecSeekError("x")) == 500


async def test_access_log_line_has_request_fields(err_client, caplog):
    with caplog.at_level(logging.INFO, logger="specseek.access"):
        await err_client.get("/missing", headers={"X-Request-ID": "req-3"})
    record = next(r for r in caplog.records if r.getMessage() == "request")
    assert (record.method, record.path, record.status) == ("GET", "/missing", 404)
    assert record.duration_ms >= 0


def test_json_formatter_outputs_one_json_object_with_extras_and_request_id():
    record = logging.LogRecord("specseek.test", logging.INFO, __file__, 1, "hello %s", ("x",), None)
    record.status = 200  # what `extra={"status": 200}` does
    token = request_id_var.set("req-4")
    try:
        line = JsonFormatter().format(record)
    finally:
        request_id_var.reset(token)

    payload = json.loads(line)
    assert "\n" not in line
    assert payload["severity"] == "INFO"
    assert payload["message"] == "hello x"
    assert payload["request_id"] == "req-4"
    assert payload["status"] == 200
