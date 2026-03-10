"""Regression tests for the P5 autonomy core preview surface."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from agentropolis.api.preview_guard import ERROR_CODE_HEADER
from agentropolis.database import get_session
from agentropolis.main import app
from agentropolis.models import Agent, AutonomyState, Base, HousekeepingLog, Region, StrategyProfile
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


def test_autonomy_routes_sync_strategy_mirror_and_reject_unsupported_sources() -> None:
    async def scenario() -> None:
        async with _seeded_client() as (client, session_factory):
            agent_response = await client.post("/api/agent/register", json={"name": "Planner One"})
            assert agent_response.status_code == 200
            agent_api_key = agent_response.json()["api_key"]

            company_response = await client.post(
                "/api/agent/company",
                headers=_api_key_headers(agent_api_key),
                json={"company_name": "Planner Works"},
            )
            assert company_response.status_code == 200

            config_response = await client.put(
                "/api/autonomy/config",
                headers=_api_key_headers(agent_api_key),
                json={
                    "autopilot_enabled": True,
                    "mode": "assisted",
                    "spending_limit_per_hour": 80,
                },
            )
            assert config_response.status_code == 200
            assert config_response.json()["mode"] == "assisted"

            standing_orders_response = await client.put(
                "/api/autonomy/standing-orders",
                headers=_api_key_headers(agent_api_key),
                json={
                    "standing_orders": {
                        "buy_rules": [
                            {
                                "resource": "H2O",
                                "below_price": 7,
                                "max_qty": 5,
                            }
                        ],
                        "sell_rules": [],
                    }
                },
            )
            assert standing_orders_response.status_code == 200
            assert standing_orders_response.json()["standing_orders"]["buy_rules"][0]["resource"] == "H2O"

            mirror_response = await client.get(
                "/api/strategy/standing-orders",
                headers=_api_key_headers(agent_api_key),
            )
            assert mirror_response.status_code == 200
            mirrored_entry = next(
                entry
                for entry in mirror_response.json()["standing_orders"]
                if entry["agent_name"] == "Planner One"
            )
            assert mirrored_entry["standing_orders"]["buy_rules"][0]["resource"] == "H2O"

            invalid_response = await client.put(
                "/api/autonomy/standing-orders",
                headers=_api_key_headers(agent_api_key),
                json={
                    "standing_orders": {
                        "buy_rules": [
                            {
                                "resource": "RAT",
                                "below_price": 12,
                                "max_qty": 5,
                                "source": "npc",
                            }
                        ],
                        "sell_rules": [],
                    }
                },
            )
            assert invalid_response.status_code == 422
            assert invalid_response.json()["error_code"] == "autonomy_rule_unsupported"
            assert invalid_response.headers[ERROR_CODE_HEADER] == "autonomy_rule_unsupported"

            async with session_factory() as session:
                agent = (
                    await session.execute(select(Agent).where(Agent.name == "Planner One"))
                ).scalar_one()
                state = (
                    await session.execute(
                        select(AutonomyState).where(AutonomyState.agent_id == agent.id)
                    )
                ).scalar_one()
                profile = (
                    await session.execute(
                        select(StrategyProfile).where(StrategyProfile.agent_id == agent.id)
                    )
                ).scalar_one()

                assert state.autopilot_enabled is True
                assert state.mode == "assisted"
                assert state.standing_orders["buy_rules"][0]["resource"] == "H2O"
                assert profile.standing_orders["buy_rules"][0]["resource"] == "H2O"

    asyncio.run(scenario())


def test_housekeeping_drives_autonomy_goal_digest_dashboard_and_intel() -> None:
    async def scenario() -> None:
        async with _seeded_client() as (client, session_factory):
            buyer_agent = await client.post("/api/agent/register", json={"name": "Buyer Pilot"})
            seller_agent = await client.post("/api/agent/register", json={"name": "Seller Pilot"})
            assert buyer_agent.status_code == 200
            assert seller_agent.status_code == 200

            buyer_agent_key = buyer_agent.json()["api_key"]
            seller_agent_key = seller_agent.json()["api_key"]

            buyer_company = await client.post(
                "/api/agent/company",
                headers=_api_key_headers(buyer_agent_key),
                json={"company_name": "Buyer Works"},
            )
            seller_company = await client.post(
                "/api/agent/company",
                headers=_api_key_headers(seller_agent_key),
                json={"company_name": "Seller Works"},
            )
            assert buyer_company.status_code == 200
            assert seller_company.status_code == 200

            buyer_company_key = buyer_company.json()["api_key"]
            seller_company_key = seller_company.json()["api_key"]

            config_response = await client.put(
                "/api/autonomy/config",
                headers=_api_key_headers(buyer_agent_key),
                json={
                    "autopilot_enabled": True,
                    "mode": "assisted",
                    "spending_limit_per_hour": 80,
                },
            )
            assert config_response.status_code == 200

            standing_orders_response = await client.put(
                "/api/autonomy/standing-orders",
                headers=_api_key_headers(buyer_agent_key),
                json={
                    "standing_orders": {
                        "buy_rules": [
                            {
                                "resource": "H2O",
                                "below_price": 7,
                                "max_qty": 5,
                            }
                        ],
                        "sell_rules": [],
                    }
                },
            )
            assert standing_orders_response.status_code == 200

            goal_response = await client.post(
                "/api/autonomy/goals",
                headers=_api_key_headers(buyer_agent_key),
                json={
                    "goal_type": "ACCUMULATE_RESOURCE",
                    "priority": 10,
                    "target": {"resource": "H2O", "quantity": 105},
                    "notes": "Keep extra water buffer",
                },
            )
            assert goal_response.status_code == 200
            goal_id = goal_response.json()["goal_id"]

            sell_response = await client.post(
                "/api/market/sell",
                headers=_api_key_headers(seller_company_key),
                json={"resource": "H2O", "quantity": 5, "price": 6},
            )
            assert sell_response.status_code == 200

            async with session_factory() as session:
                buyer = (
                    await session.execute(select(Agent).where(Agent.name == "Buyer Pilot"))
                ).scalar_one()
                buyer.hunger = 10.0
                buyer.thirst = 10.0
                buyer.energy = 10.0

                regions = (
                    await session.execute(select(Region).order_by(Region.id.asc()))
                ).scalars().all()
                destination_region_id = next(
                    region.id for region in regions if region.id != buyer.current_region_id
                )

                summary = await run_housekeeping_sweep(
                    session,
                    tick_number=30,
                    now=datetime.now(UTC),
                )
                await session.commit()

                housekeeping_log = (
                    await session.execute(
                        select(HousekeepingLog).order_by(HousekeepingLog.id.desc()).limit(1)
                    )
                ).scalar_one()

                assert summary["autonomy"]["reflex"]["actions"] >= 3
                assert summary["autonomy"]["standing_orders"]["buy_orders_created"] == 1
                assert summary["autonomy"]["goals"]["completed_now"] == 1
                assert housekeeping_log.autonomy_summary is not None
                assert housekeeping_log.digest_summary is not None

            digest_response = await client.get(
                "/api/digest",
                headers=_api_key_headers(buyer_agent_key),
            )
            dashboard_response = await client.get(
                "/api/dashboard",
                headers=_api_key_headers(buyer_agent_key),
            )
            market_intel_response = await client.get(
                "/api/intel/market/H2O",
                headers=_api_key_headers(buyer_agent_key),
            )
            route_intel_response = await client.get(
                "/api/intel/routes",
                headers=_api_key_headers(buyer_agent_key),
                params={"to_region_id": destination_region_id},
            )
            opportunities_response = await client.get(
                "/api/intel/opportunities",
                headers=_api_key_headers(buyer_agent_key),
            )

            assert digest_response.status_code == 200
            assert dashboard_response.status_code == 200
            assert market_intel_response.status_code == 200
            assert route_intel_response.status_code == 200
            assert opportunities_response.status_code == 200

            digest_body = digest_response.json()
            assert digest_body["unread_count"] >= 1
            assert any(item["event_type"] == "goal_completed" for item in digest_body["notifications"])
            assert any(item["goal_id"] == goal_id for item in digest_body["goal_updates"])
            assert any(item["decision_type"] == "TRADE" for item in digest_body["recent_decisions"])

            dashboard_body = dashboard_response.json()
            assert dashboard_body["autonomy"]["mode"] == "assisted"
            assert dashboard_body["digest_unread_count"] >= 1
            assert any(goal["goal_id"] == goal_id and goal["status"] == "COMPLETED" for goal in dashboard_body["goals"])

            market_intel_body = market_intel_response.json()
            assert market_intel_body["ticker"] == "H2O"
            assert market_intel_body["order_book"]["ticker"] == "H2O"

            route_body = route_intel_response.json()
            assert route_body["to_region_id"] == destination_region_id
            assert route_body["path"][0] == dashboard_body["agent"]["current_region_id"]

            opportunities_body = opportunities_response.json()
            assert opportunities_body["agent_id"] == dashboard_body["agent"]["agent_id"]
            assert any(item["category"] == "company_context" for item in opportunities_body["opportunities"])

            inventory_response = await client.get(
                "/api/inventory/H2O",
                headers=_api_key_headers(buyer_company_key),
            )
            assert inventory_response.status_code == 200
            assert inventory_response.json()["quantity"] >= 105.0

    asyncio.run(scenario())
