"""Observability endpoint smoke tests."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import agentropolis.mcp._shared as mcp_shared
from agentropolis.database import get_session
from agentropolis.main import app
from agentropolis.mcp.tools_agent import get_agent_status, register_agent
from agentropolis.mcp.tools_company import create_company
from agentropolis.mcp.tools_market import get_market_prices
from agentropolis.middleware.metrics import reset_request_metrics_state
from agentropolis.models import Base
from agentropolis.mcp.metrics import reset_mcp_metrics_state
from agentropolis.services.game_engine import run_housekeeping_sweep
from agentropolis.services.seed import seed_game_data
from agentropolis.services.seed_world import seed_world


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

    original_async_session = mcp_shared.async_session
    mcp_shared.async_session = session_factory
    app.dependency_overrides[get_session] = override_get_session
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            yield client, session_factory
    finally:
        app.dependency_overrides.clear()
        mcp_shared.async_session = original_async_session
        await engine.dispose()


def test_observability_endpoint_reports_request_and_housekeeping_data() -> None:
    async def scenario() -> None:
        reset_request_metrics_state()
        reset_mcp_metrics_state()
        async with _seeded_client() as (client, session_factory):
            await client.get("/health")
            await client.get("/meta/runtime")
            await client.get("/api/game/status")

            agent = await register_agent("Observability MCP")
            assert agent["ok"] is True
            company = await create_company(agent["agent"]["api_key"], "Observability Company")
            assert company["ok"] is True
            agent_status = await get_agent_status(agent["agent"]["api_key"])
            market_prices = await get_market_prices(company["company"]["api_key"])
            assert agent_status["ok"] is True
            assert market_prices["ok"] is True

            async with session_factory() as session:
                await run_housekeeping_sweep(session, tick_number=7, now=datetime.now(UTC))
                await session.commit()

            response = await client.get("/meta/observability")
            assert response.status_code == 200

            payload = response.json()
            assert payload["requests"]["requests_total"] >= 3
            assert payload["requests"]["by_actor_kind"]["public"] >= 1
            assert payload["mcp"]["calls_total"] >= 4
            assert payload["mcp"]["by_actor_kind"]["public"] >= 1
            assert payload["mcp"]["by_actor_kind"]["agent"] >= 1
            assert payload["mcp"]["by_actor_kind"]["company"] >= 1
            assert "register_agent" in payload["mcp"]["by_tool"]
            assert payload["concurrency"]["authenticated_request_scope"] == "all"
            assert payload["concurrency"]["entity_lock_scope"] == "writes_only"
            assert payload["concurrency"]["request_slots"]["capacity"] >= 1
            assert payload["concurrency"]["housekeeping_slots"]["capacity"] >= 1
            assert payload["concurrency"]["rate_limits"]["agent"] >= 1
            assert payload["economy"]["thresholds"]["inflation_index"]["warning_above"] > 1.0
            assert payload["economy"]["source_sink_proxy"]["tax_collected_total"] >= 0
            assert "pending_execution_jobs" in payload["economy"]["stuck_work_signals"]
            assert "reflex_actions" in payload["agent_behavior"]
            assert payload["housekeeping"]["latest_sweep"]["sweep_count"] == 7
            assert payload["housekeeping"]["latest_sweep"]["trigger_kind"] == "scheduled"
            assert payload["housekeeping"]["recent_sweeps"][0]["sweep_count"] == 7
            assert payload["housekeeping"]["average_duration_seconds_recent"] >= 0.0
            assert payload["execution"]["job_states"][-1] == "dead_letter"
            assert payload["execution"]["housekeeping_phase_contract"]["phase_results_logged"] is True
            assert payload["execution"]["lag"]["warning_threshold_seconds"] >= 1

    asyncio.run(scenario())
