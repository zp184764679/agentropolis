"""Core MCP preview-surface tests for P5 autonomy."""

from __future__ import annotations

import asyncio
import importlib
from contextlib import asynccontextmanager

from fastapi.routing import Mount
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import agentropolis.mcp._shared as mcp_shared
from agentropolis.config import settings
from agentropolis.database import get_session
import agentropolis.main as main_module
from agentropolis.main import app
from agentropolis.mcp.server import mcp
from agentropolis.mcp.tools_agent import (
    acknowledge_digest_tool,
    create_goal_tool,
    get_autonomy_config_tool,
    get_dashboard_tool,
    get_digest_tool,
    get_standing_orders_tool,
    list_goals_tool,
    update_autonomy_config_tool,
    update_standing_orders_tool,
)
from agentropolis.models import Base
from agentropolis.services.game_engine import run_housekeeping_sweep
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
            yield client, session_factory
    finally:
        app.dependency_overrides.clear()
        mcp_shared.async_session = original_async_session
        await engine.dispose()


def test_mcp_core_registry_and_streamable_mount() -> None:
    tool_names = set(mcp._tool_manager._tools)
    expected = {
        "get_agent_status_tool",
        "create_company_tool",
        "get_company_tool",
        "get_autonomy_config_tool",
        "update_autonomy_config_tool",
        "get_standing_orders_tool",
        "update_standing_orders_tool",
        "get_digest_tool",
        "acknowledge_digest_tool",
        "get_dashboard_tool",
        "list_goals_tool",
        "create_goal_tool",
        "update_goal_tool",
        "get_market_intel_tool",
        "get_route_intel_tool",
        "get_opportunities_tool",
    }

    assert expected.issubset(tool_names)
    assert len(tool_names) >= 38
    assert callable(mcp.streamable_http_app())

    original_enabled = settings.MCP_SURFACE_ENABLED
    try:
        settings.MCP_SURFACE_ENABLED = True
        reloaded = importlib.reload(main_module)
        assert any(
            isinstance(route, Mount) and route.path == "/mcp"
            for route in reloaded.app.router.routes
        )
    finally:
        settings.MCP_SURFACE_ENABLED = original_enabled
        importlib.reload(main_module)


def test_mcp_autonomy_tools_match_rest_surface() -> None:
    async def scenario() -> None:
        async with _seeded_client() as (client, session_factory):
            seller_agent = await client.post("/api/agent/register", json={"name": "MCP Seller"})
            buyer_agent = await client.post("/api/agent/register", json={"name": "MCP Buyer"})
            assert seller_agent.status_code == 200
            assert buyer_agent.status_code == 200

            seller_agent_key = seller_agent.json()["api_key"]
            buyer_agent_key = buyer_agent.json()["api_key"]

            seller_company = await client.post(
                "/api/agent/company",
                headers=_api_key_headers(seller_agent_key),
                json={"company_name": "MCP Seller Works"},
            )
            buyer_company = await client.post(
                "/api/agent/company",
                headers=_api_key_headers(buyer_agent_key),
                json={"company_name": "MCP Buyer Works"},
            )
            assert seller_company.status_code == 200
            assert buyer_company.status_code == 200

            seller_company_key = seller_company.json()["api_key"]

            updated_config = await update_autonomy_config_tool(
                buyer_agent_key,
                autopilot_enabled=True,
                mode="assisted",
                spending_limit_per_hour=80,
            )
            assert updated_config["ok"] is True

            updated_orders = await update_standing_orders_tool(
                buyer_agent_key,
                {
                    "buy_rules": [
                        {
                            "resource": "H2O",
                            "below_price": 7,
                            "max_qty": 5,
                        }
                    ],
                    "sell_rules": [],
                },
            )
            assert updated_orders["ok"] is True

            created_goal = await create_goal_tool(
                buyer_agent_key,
                "ACCUMULATE_RESOURCE",
                {"resource": "H2O", "quantity": 105},
                priority=5,
                notes="MCP parity goal",
            )
            assert created_goal["ok"] is True

            sell_response = await client.post(
                "/api/market/sell",
                headers=_api_key_headers(seller_company_key),
                json={"resource": "H2O", "quantity": 5, "price": 6},
            )
            assert sell_response.status_code == 200

            async with session_factory() as session:
                await run_housekeeping_sweep(session, tick_number=30)
                await session.commit()

            rest_config = await client.get(
                "/api/autonomy/config",
                headers=_api_key_headers(buyer_agent_key),
            )
            rest_digest = await client.get(
                "/api/digest",
                headers=_api_key_headers(buyer_agent_key),
            )
            rest_dashboard = await client.get(
                "/api/dashboard",
                headers=_api_key_headers(buyer_agent_key),
            )

            assert rest_config.status_code == 200
            assert rest_digest.status_code == 200
            assert rest_dashboard.status_code == 200

            mcp_config = await get_autonomy_config_tool(buyer_agent_key)
            mcp_orders = await get_standing_orders_tool(buyer_agent_key)
            mcp_goals = await list_goals_tool(buyer_agent_key)
            mcp_digest = await get_digest_tool(buyer_agent_key)
            mcp_dashboard = await get_dashboard_tool(buyer_agent_key)
            mcp_ack = await acknowledge_digest_tool(buyer_agent_key)

            assert mcp_config["ok"] is True
            assert mcp_orders["ok"] is True
            assert mcp_goals["ok"] is True
            assert mcp_digest["ok"] is True
            assert mcp_dashboard["ok"] is True
            assert mcp_ack["ok"] is True

            assert mcp_config["config"] == rest_config.json()
            assert mcp_orders["standing_orders"]["buy_rules"][0]["resource"] == "H2O"
            assert any(goal["status"] == "COMPLETED" for goal in mcp_goals["goals"])
            assert mcp_digest["digest"]["agent_id"] == rest_digest.json()["agent_id"]
            assert mcp_digest["digest"]["goal_updates"] == rest_digest.json()["goal_updates"]
            assert mcp_dashboard["dashboard"]["agent"]["agent_id"] == rest_dashboard.json()["agent"]["agent_id"]
            assert mcp_dashboard["dashboard"]["autonomy"] == rest_dashboard.json()["autonomy"]
            assert mcp_ack["digest"]["agent_id"] == rest_digest.json()["agent_id"]

    asyncio.run(scenario())
