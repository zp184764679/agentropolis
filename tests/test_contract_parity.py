"""REST/MCP contract parity smoke tests."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import agentropolis.mcp._shared as mcp_shared
from agentropolis.database import get_session
from agentropolis.main import app
from agentropolis.mcp.tools_agent import register_agent
from agentropolis.mcp.tools_company import create_company, get_company
from agentropolis.mcp.tools_intel import get_game_status, get_market_intel
from agentropolis.models import Base
from agentropolis.services.seed import seed_game_data
from agentropolis.services.seed_world import seed_world


def _api_key_headers(api_key: str) -> dict[str, str]:
    return {"X-API-Key": api_key}


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
            yield client
    finally:
        app.dependency_overrides.clear()
        mcp_shared.async_session = original_async_session
        await engine.dispose()


def test_rest_and_mcp_share_company_game_and_intel_contracts() -> None:
    async def scenario() -> None:
        async with _seeded_client() as client:
            agent = await register_agent("Parity Agent")
            assert agent["ok"] is True

            agent_api_key = agent["agent"]["api_key"]
            created_company = await create_company(agent_api_key, "Parity Works")
            assert created_company["ok"] is True

            rest_company = await client.get(
                "/api/agent/company",
                headers=_api_key_headers(agent_api_key),
            )
            rest_game = await client.get("/api/game/status")
            rest_intel = await client.get(
                "/api/intel/market/H2O",
                headers=_api_key_headers(agent_api_key),
            )

            assert rest_company.status_code == 200
            assert rest_game.status_code == 200
            assert rest_intel.status_code == 200

            mcp_company = await get_company(agent_api_key)
            mcp_game = await get_game_status()
            mcp_intel = await get_market_intel(agent_api_key, "H2O")

            assert mcp_company["ok"] is True
            assert mcp_game["ok"] is True
            assert mcp_intel["ok"] is True

            assert mcp_company["company"] == rest_company.json()
            assert mcp_game["status"] == rest_game.json()
            assert mcp_intel["intel"] == rest_intel.json()

    asyncio.run(scenario())
