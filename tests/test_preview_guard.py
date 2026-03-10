"""Regression tests for preview-route control-plane guardrails."""

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from agentropolis.api.auth import get_current_agent
from agentropolis.api.preview_guard import (
    require_agent_preview_write,
    reset_preview_guard_state,
)
from agentropolis.config import settings
from agentropolis.database import get_session
from agentropolis.main import app
from agentropolis.models import Base


@asynccontextmanager
async def _preview_client(*, agent_id: int | None = None):
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_session():
        async with session_factory() as session:
            yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    app.dependency_overrides[get_session] = override_get_session

    if agent_id is not None:
        async def override_current_agent():
            return SimpleNamespace(id=agent_id)

        app.dependency_overrides[get_current_agent] = override_current_agent

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            yield client
    finally:
        app.dependency_overrides.clear()
        reset_preview_guard_state()
        await engine.dispose()


def test_preview_guard_rate_limits_agent_mutations(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "PREVIEW_AGENT_MUTATIONS_PER_WINDOW", 1)
    monkeypatch.setattr(settings, "PREVIEW_MUTATION_WINDOW_SECONDS", 60)
    reset_preview_guard_state()

    async def scenario() -> None:
        actor = SimpleNamespace(id=42)

        await require_agent_preview_write(actor)

        with pytest.raises(HTTPException) as excinfo:
            await require_agent_preview_write(actor)

        assert excinfo.value.status_code == 429
        assert excinfo.value.detail == "Preview mutation rate limit exceeded."

    try:
        asyncio.run(scenario())
    finally:
        reset_preview_guard_state()


def test_preview_surface_kill_switch_blocks_reads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "PREVIEW_SURFACE_ENABLED", False)
    reset_preview_guard_state()

    async def scenario() -> None:
        async with _preview_client() as client:
            response = await client.get("/api/world/map")

        assert response.status_code == 503
        assert response.json()["detail"] == "Preview surface is disabled by runtime policy."

    asyncio.run(scenario())


def test_preview_write_gate_blocks_registration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "PREVIEW_WRITES_ENABLED", False)
    reset_preview_guard_state()

    async def scenario() -> None:
        async with _preview_client() as client:
            response = await client.post(
                "/api/agent/register",
                json={"name": "Blocked Agent"},
            )

        assert response.status_code == 503
        assert response.json()["detail"] == "Preview write operations are disabled by runtime policy."

    asyncio.run(scenario())


def test_warfare_toggle_blocks_preview_mutations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "WARFARE_MUTATIONS_ENABLED", False)
    reset_preview_guard_state()

    async def scenario() -> None:
        async with _preview_client(agent_id=7) as client:
            response = await client.post(
                "/api/warfare/contracts",
                json={
                    "mission_type": "raid_transport",
                    "target_region_id": 1,
                    "reward_per_agent": 100,
                    "max_agents": 1,
                },
            )

        assert response.status_code == 503
        assert response.json()["detail"] == (
            "Warfare preview mutations are disabled by runtime policy."
        )

    asyncio.run(scenario())
