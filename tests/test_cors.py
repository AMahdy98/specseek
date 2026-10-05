"""CORS: which browser origins may call the API, and what they are allowed to see."""

from app.config import parse_origins

UI = "http://localhost:5173"
STRANGER = "https://evil.example"
PREFLIGHT = {
    "Access-Control-Request-Method": "POST",
    "Access-Control-Request-Headers": "content-type",
}


def test_parse_origins_trims_and_drops_empties():
    assert parse_origins(" http://a:1/ , ,http://b:2") == ("http://a:1", "http://b:2")
    assert parse_origins("") == ()


async def test_preflight_from_the_ui_origin_is_allowed(client):
    resp = await client.options("/v1/query", headers={"Origin": UI, **PREFLIGHT})
    assert resp.status_code == 200
    assert resp.headers["access-control-allow-origin"] == UI
    assert "POST" in resp.headers["access-control-allow-methods"]
    assert resp.headers["access-control-max-age"] == "600"


async def test_preflight_from_another_origin_is_refused(client):
    resp = await client.options("/v1/query", headers={"Origin": STRANGER, **PREFLIGHT})
    assert resp.status_code == 400
    assert "access-control-allow-origin" not in resp.headers


async def test_response_to_the_ui_origin_exposes_request_id_and_timing(client, db_up):
    db_up(True)
    resp = await client.get("/v1/health", headers={"Origin": UI})
    assert resp.headers["access-control-allow-origin"] == UI
    exposed = resp.headers["access-control-expose-headers"]
    assert "X-Request-ID" in exposed and "Server-Timing" in exposed


async def test_error_responses_carry_cors_headers_too(client):
    # Otherwise the browser reports a bare network failure and the UI cannot show our message.
    resp = await client.get("/v1/nope", headers={"Origin": UI})
    assert resp.status_code == 404
    assert resp.headers["access-control-allow-origin"] == UI
    assert resp.json()["error"]["code"] == "not_found"


async def test_another_origin_still_gets_an_answer_but_no_permission_to_read_it(client, db_up):
    # CORS is enforced by the browser, not the server: the request is served either way.
    db_up(True)
    resp = await client.get("/v1/health", headers={"Origin": STRANGER})
    assert resp.status_code == 200
    assert "access-control-allow-origin" not in resp.headers
