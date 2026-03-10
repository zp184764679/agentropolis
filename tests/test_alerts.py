"""Derived alerts endpoint and export tests."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from agentropolis.database import get_session
from agentropolis.main import app
from agentropolis.models import Base
from agentropolis.services.seed import seed_game_data
from agentropolis.services.seed_world import seed_world
from scripts.export_alert_snapshot import build_alert_export


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
            yield client, session_factory
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()


def test_alerts_endpoint_and_export_report_gate_and_housekeeping_state() -> None:
    async def scenario() -> None:
        async with _seeded_client() as (client, session_factory):
            response = await client.get("/meta/alerts")
            assert response.status_code == 200
            payload = response.json()

            codes = {entry["code"] for entry in payload["alerts"]}
            assert "housekeeping_missing" in codes
            assert any(code.startswith("rollout_gate_blocked:") for code in codes)
            assert payload["summary"]["warning"] >= 1
            assert payload["sources"]["observability_endpoint"] == "/meta/observability"

            exported = await build_alert_export(session_factory=session_factory)
            assert "alerts" in exported
            assert exported["alerts"]["summary"]["has_blocking_failures"] is True

    asyncio.run(scenario())
