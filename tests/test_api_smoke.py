"""Smoke tests against FastAPI: routing, auth, basic endpoint shapes.

We import the app AFTER conftest forced env overrides, so the app uses the
test DB. We do NOT hit Stockfish / Ollama / Arq — only thin endpoints.
"""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from tests.factories import make_player


pytestmark = pytest.mark.db


def _build_client(db_session=None) -> AsyncClient:
    from app.db.session import get_session
    from app.main import create_app
    app = create_app()
    if db_session is not None:
        async def _override_get_session():
            yield db_session
        app.dependency_overrides[get_session] = _override_get_session
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_health_endpoint_is_public() -> None:
    async with _build_client() as client:
        r = await client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert "checks" in data


async def test_v1_endpoint_requires_api_key(db_session) -> None:
    await make_player(db_session, "alice", is_me=True)
    async with _build_client(db_session) as client:
        r = await client.get("/api/v1/coach/me/dashboard")
    assert r.status_code == 401


async def test_v1_dashboard_with_valid_key(db_session) -> None:
    await make_player(db_session, "alice", is_me=True)
    async with _build_client(db_session) as client:
        r = await client.get(
            "/api/v1/coach/me/dashboard",
            headers={"X-API-Key": "test-key"},
        )
    assert r.status_code == 200
    data = r.json()
    assert data["player"]["chesscom_username"] == "alice"
    assert "weaknesses" in data
    assert "training" in data
    assert "recent_games" in data


async def test_docs_is_public() -> None:
    async with _build_client() as client:
        r = await client.get("/docs")
    assert r.status_code == 200
    assert "swagger" in r.text.lower()
