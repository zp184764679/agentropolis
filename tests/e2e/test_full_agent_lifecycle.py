"""Full local-preview external-agent lifecycle using bootstrap scripts plus MCP/REST."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import agentropolis.mcp._shared as mcp_shared
from agentropolis.database import get_session
from agentropolis.main import app
from agentropolis.mcp.tools_intel import get_market_intel
from agentropolis.mcp.tools_market import place_sell_order
from agentropolis.mcp.tools_strategy import autonomy_tool, briefing_tool, digest_tool
from agentropolis.models import Base
from agentropolis.services.game_engine import run_housekeeping_sweep
from agentropolis.services.seed import seed_game_data
from agentropolis.services.seed_world import seed_world
from scripts.monitor_agents import collect_fleet_snapshot
from scripts.register_agents import bootstrap_agents


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


def test_full_local_preview_agent_lifecycle() -> None:
    async def scenario() -> None:
        async with _seeded_client() as (client, session_factory):
            manifest = await bootstrap_agents(
                client,
                [
                    {
                        "agent_name": "OpenClaw Buyer",
                        "company_name": "Buyer Works",
                        "autonomy_config": {
                            "autopilot_enabled": True,
                            "mode": "assisted",
                            "spending_limit_per_hour": 120,
                        },
                        "standing_orders": {
                            "buy_rules": [{"resource": "H2O", "below_price": 7, "max_qty": 5}],
                            "sell_rules": [],
                        },
                    },
                    {
                        "agent_name": "OpenClaw Seller",
                        "company_name": "Seller Works",
                        "autonomy_config": {
                            "autopilot_enabled": True,
                            "mode": "assisted",
                            "spending_limit_per_hour": 120,
                        },
                        "standing_orders": {"buy_rules": [], "sell_rules": []},
                    },
                ],
                base_url="http://testserver",
            )

            buyer = manifest["agents"][0]
            seller = manifest["agents"][1]

            sell_order = await place_sell_order(
                seller["agent_api_key"],
                resource="H2O",
                quantity=5,
                price=6,
            )
            assert sell_order["ok"] is True

            async with session_factory() as session:
                await run_housekeeping_sweep(session, tick_number=30)
                await session.commit()

            config = await autonomy_tool(buyer["agent_api_key"], action="get_config")
            digest = await digest_tool(buyer["agent_api_key"], action="get")
            dashboard = await briefing_tool(buyer["agent_api_key"], section="dashboard")
            intel = await get_market_intel(buyer["agent_api_key"], resource="H2O")
            snapshot = await collect_fleet_snapshot(client, manifest)

            assert manifest["prompt_file"] == "prompts/agent-brain.md"
            assert manifest["skill_file"] == "skills/agentropolis-world/SKILL.md"
            assert manifest["mcp_url"] == "http://testserver/mcp"
            assert config["ok"] is True
            assert config["config"]["autopilot_enabled"] is True
            assert digest["ok"] is True
            assert dashboard["ok"] is True
            assert dashboard["briefing"]["company"]["name"] == "Buyer Works"
            assert intel["ok"] is True
            assert intel["intel"]["ticker"] == "H2O"
            assert snapshot["game_status"]["ok"] is True
            assert snapshot["leaderboard"]["ok"] is True
            assert len(snapshot["agents"]) == 2
            assert snapshot["agents"][0]["company_name"] == "Buyer Works"
            assert snapshot["agents"][0]["autonomy_mode"] == "assisted"

    asyncio.run(scenario())
