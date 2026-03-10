"""P6 Wave 1 MCP surface tests."""

from __future__ import annotations

import asyncio
import importlib
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi.routing import Mount
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import agentropolis.main as main_module
import agentropolis.mcp._shared as mcp_shared
from agentropolis.config import settings
from agentropolis.database import get_session
from agentropolis.main import app
from agentropolis.mcp.server import mcp
from agentropolis.mcp.tools_agent import (
    get_agent_profile,
    get_agent_status,
    register_agent,
)
from agentropolis.mcp.tools_company import create_company, get_company
from agentropolis.mcp.tools_intel import get_game_status, get_leaderboard, get_market_intel
from agentropolis.mcp.tools_market import place_sell_order
from agentropolis.mcp.tools_notifications import get_notifications, mark_notification_read
from agentropolis.mcp.tools_npc import get_shop_effective_prices, list_region_shops
from agentropolis.mcp.tools_skills import get_my_skills, get_skill_definitions
from agentropolis.mcp.tools_social import (
    create_guild,
    join_guild,
    leave_guild,
    list_guilds,
    relationship_tool,
    treaty_tool,
)
from agentropolis.mcp.tools_strategy import autonomy_tool, briefing_tool, digest_tool
from agentropolis.mcp.tools_transport import (
    create_transport,
    get_my_transports,
    get_transport_status,
)
from agentropolis.mcp.tools_warfare import (
    contract_action_tool,
    create_contract,
    get_region_threats,
    list_contracts,
)
from agentropolis.mcp.tools_world import get_region_info, get_route, get_world_map
from agentropolis.models import Base
from agentropolis.services import notification_svc
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


def test_mcp_wave1_registry_and_streamable_mount() -> None:
    tool_names = set(mcp._tool_manager._tools)
    expected = {
        "register_agent",
        "get_agent_status",
        "create_company",
        "get_company",
        "get_world_map",
        "get_region_info",
        "get_route",
        "get_inventory",
        "get_resource_info",
        "get_market_prices",
        "get_trade_history",
        "list_region_shops",
        "get_shop_effective_prices",
        "create_transport",
        "get_my_transports",
        "get_skill_definitions",
        "create_guild",
        "treaty_tool",
        "relationship_tool",
        "create_contract",
        "contract_action_tool",
        "strategy_profile_tool",
        "autonomy_tool",
        "digest_tool",
        "briefing_tool",
        "get_notifications",
        "mark_notification_read",
        "get_game_status",
        "get_leaderboard",
    }

    assert expected.issubset(tool_names)
    assert len(tool_names) == 60
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


def test_mcp_wave1_strategy_tools_match_rest_surface() -> None:
    async def scenario() -> None:
        async with _seeded_client() as (client, session_factory):
            seller_agent = await register_agent("MCP Seller")
            buyer_agent = await register_agent("MCP Buyer")
            assert seller_agent["ok"] is True
            assert buyer_agent["ok"] is True

            seller_agent_key = seller_agent["agent"]["api_key"]
            buyer_agent_key = buyer_agent["agent"]["api_key"]

            seller_company = await create_company(seller_agent_key, "MCP Seller Works")
            buyer_company = await create_company(buyer_agent_key, "MCP Buyer Works")
            assert seller_company["ok"] is True
            assert buyer_company["ok"] is True

            seller_company_key = seller_company["company"]["api_key"]

            updated_config = await autonomy_tool(
                buyer_agent_key,
                action="update_config",
                autopilot_enabled=True,
                mode="assisted",
                spending_limit_per_hour=80,
            )
            updated_orders = await autonomy_tool(
                buyer_agent_key,
                action="update_standing_orders",
                standing_orders={
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
            created_goal = await autonomy_tool(
                buyer_agent_key,
                action="create_goal",
                goal_type="ACCUMULATE_RESOURCE",
                target={"resource": "H2O", "quantity": 105},
                priority=5,
                notes="MCP parity goal",
            )
            assert updated_config["ok"] is True
            assert updated_orders["ok"] is True
            assert created_goal["ok"] is True

            sell_order = await place_sell_order(
                seller_company_key,
                resource="H2O",
                quantity=5,
                price=6,
            )
            assert sell_order["ok"] is True

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

            mcp_config = await autonomy_tool(buyer_agent_key, action="get_config")
            mcp_orders = await autonomy_tool(buyer_agent_key, action="get_standing_orders")
            mcp_goals = await autonomy_tool(buyer_agent_key, action="list_goals")
            mcp_digest = await digest_tool(buyer_agent_key, action="get")
            mcp_dashboard = await briefing_tool(buyer_agent_key, section="dashboard")
            mcp_ack = await digest_tool(buyer_agent_key, action="ack")

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
            assert mcp_dashboard["briefing"]["agent"]["agent_id"] == rest_dashboard.json()["agent"]["agent_id"]
            assert mcp_dashboard["briefing"]["autonomy"] == rest_dashboard.json()["autonomy"]
            assert mcp_ack["digest"]["agent_id"] == rest_digest.json()["agent_id"]

    asyncio.run(scenario())


def test_mcp_wave1_expanded_surface_smoke() -> None:
    async def scenario() -> None:
        async with _seeded_client() as (_client, session_factory):
            primary = await register_agent("Wave1 Primary")
            secondary = await register_agent("Wave1 Secondary")
            assert primary["ok"] is True
            assert secondary["ok"] is True

            primary_agent_key = primary["agent"]["api_key"]
            secondary_agent_key = secondary["agent"]["api_key"]

            primary_company = await create_company(primary_agent_key, "Wave1 Works")
            secondary_company = await create_company(secondary_agent_key, "Wave1 Backup")
            assert primary_company["ok"] is True
            assert secondary_company["ok"] is True

            primary_company_key = primary_company["company"]["api_key"]

            status = await get_agent_status(primary_agent_key)
            profile = await get_agent_profile(primary_agent_key, primary["agent"]["agent_id"])
            company = await get_company(primary_agent_key)
            world_map = await get_world_map(primary_agent_key)
            route = await get_route(primary_agent_key, to_region_id=2)
            region = await get_region_info(primary_agent_key, region_id=1)
            inventory_item = await get_market_intel(primary_agent_key, "H2O")
            skills = await get_skill_definitions(primary_agent_key)
            my_skills = await get_my_skills(primary_agent_key)
            shops = await list_region_shops(primary_agent_key)
            shop_prices = await get_shop_effective_prices(primary_agent_key, shop_id=1)
            transport = await create_transport(
                primary_agent_key,
                from_region_id=1,
                to_region_id=2,
                items={"RAT": 1},
            )
            guild = await create_guild(primary_agent_key, "Wave1 Guild", home_region_id=1)
            guilds = await list_guilds(primary_agent_key)
            joined = await join_guild(secondary_agent_key, guild["guild"]["guild_id"])
            left = await leave_guild(secondary_agent_key, guild["guild"]["guild_id"])
            relation = await relationship_tool(
                primary_agent_key,
                action="set",
                target_agent_id=secondary["agent"]["agent_id"],
                relation_type="allied",
                trust_delta=5,
            )
            treaty = await treaty_tool(
                primary_agent_key,
                action="propose",
                treaty_type="alliance",
                target_agent_id=secondary["agent"]["agent_id"],
                terms={"scope": "trade"},
            )
            accepted = await treaty_tool(
                secondary_agent_key,
                action="accept",
                treaty_id=treaty["treaty"]["treaty_id"],
            )
            contract = await create_contract(
                primary_agent_key,
                mission_type="raid_transport",
                target_region_id=2,
                reward_per_agent=100,
                max_agents=1,
                target_transport_id=transport["transport"]["transport_id"],
            )
            contracts = await list_contracts(primary_agent_key, limit=10)
            enlist = await contract_action_tool(
                secondary_agent_key,
                action="enlist",
                contract_id=contract["contract"]["contract_id"],
            )
            threats = await get_region_threats(primary_agent_key, region_id=2)
            game_status = await get_game_status()
            leaderboard = await get_leaderboard()

            async with session_factory() as session:
                await notification_svc.notify(
                    session,
                    primary["agent"]["agent_id"],
                    "system",
                    "Wave1",
                    "Smoke test notification",
                )
                await session.commit()

            notifications = await get_notifications(primary_agent_key)
            mark_read = await mark_notification_read(
                primary_agent_key,
                notifications["notifications"]["notifications"][0]["notification_id"],
            )
            transport_status = await get_transport_status(
                primary_agent_key,
                transport["transport"]["transport_id"],
            )
            transports = await get_my_transports(primary_agent_key)

            for payload in (
                status,
                profile,
                company,
                world_map,
                route,
                region,
                inventory_item,
                skills,
                my_skills,
                shops,
                shop_prices,
                transport,
                guild,
                guilds,
                joined,
                left,
                relation,
                treaty,
                accepted,
                contract,
                contracts,
                enlist,
                threats,
                game_status,
                leaderboard,
                notifications,
                mark_read,
                transport_status,
                transports,
            ):
                assert payload["ok"] is True

    asyncio.run(scenario())


def test_agentropolis_world_skill_files_exist_and_link_references() -> None:
    root = Path(__file__).resolve().parents[1] / "skills" / "agentropolis-world"
    skill = root / "SKILL.md"
    matrix = root / "references" / "tool-matrix.md"
    fallback = root / "references" / "rest-fallback-map.md"

    assert skill.exists()
    assert matrix.exists()
    assert fallback.exists()

    skill_text = skill.read_text(encoding="utf-8")
    assert "tool-matrix.md" in skill_text
    assert "rest-fallback-map.md" in skill_text
