"""Rollout readiness and artifact tests."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from agentropolis.database import get_session
from agentropolis.main import app
from agentropolis.models import Base
from agentropolis.services.seed import seed_game_data
from agentropolis.services.seed_world import seed_world
from scripts.export_contract_snapshot import build_contract_snapshot


@asynccontextmanager
async def _seeded_client():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_session():
        async with session_factory() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        await seed_game_data(session)
        await seed_world(session)
        await session.commit()

    app.dependency_overrides[get_session] = override_get_session
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            yield client
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()


def test_rollout_readiness_endpoint_and_artifacts_exist() -> None:
    async def scenario() -> None:
        async with _seeded_client() as client:
            response = await client.get("/meta/rollout-readiness")
            assert response.status_code == 200
            payload = response.json()

            assert payload["local_preview_only"] is True
            assert "mcp_surface_enabled" in payload["gates"]
            assert "admin_token_configured" in payload["gates"]
            assert "control_contract" in payload["gates"]
            assert isinstance(payload["blocking_failures"], list)

    asyncio.run(scenario())

    snapshot = build_contract_snapshot()
    assert snapshot["mcp_registry"]["tool_count"] >= 60
    assert snapshot["runtime_meta"]["rollout_readiness_surface"]["endpoint"] == "/meta/rollout-readiness"

    expected_paths = [
        Path("scripts/export_contract_snapshot.py"),
        Path("scripts/check_rollout_gate.py"),
        Path("docs/local-preview-rollout.md"),
        Path("docs/recovery-runbook.md"),
    ]
    for path in expected_paths:
        assert path.exists(), f"Missing rollout artifact: {path}"
