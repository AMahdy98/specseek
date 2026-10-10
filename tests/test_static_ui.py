"""Serving the built UI from the API process (as the Docker image does)."""

import httpx
import pytest
from fastapi import FastAPI

from app.api.error_handlers import install_error_handlers
from app.api.routes import database_is_up, router
from app.main import mount_ui


@pytest.fixture
async def site(tmp_path):
    """A fresh app wired like app.main, with a fake built UI in a temp folder."""
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<!doctype html><title>SpecSeek</title>")
    (tmp_path / "assets" / "app.js").write_text("console.log('ui')")

    app = FastAPI()
    install_error_handlers(app)
    app.include_router(router, prefix="/v1")
    mount_ui(app, tmp_path)
    app.dependency_overrides[database_is_up] = lambda: True
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client


async def test_the_root_path_serves_the_ui(site):
    resp = await site.get("/")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")
    assert "<title>SpecSeek</title>" in resp.text


async def test_built_assets_are_served_with_their_content_type(site):
    resp = await site.get("/assets/app.js")
    assert resp.status_code == 200
    assert "javascript" in resp.headers["content-type"]


async def test_the_api_still_answers_under_v1(site):
    resp = await site.get("/v1/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "database": "ok"}


async def test_an_unknown_api_path_is_still_a_json_404_not_the_ui(site):
    resp = await site.get("/v1/nope")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "not_found"


async def test_files_outside_the_ui_folder_cannot_be_read(site):
    resp = await site.get("/../pyproject.toml")
    assert resp.status_code == 404
    resp = await site.get("/%2e%2e/%2e%2e/etc/passwd")
    assert resp.status_code == 404
