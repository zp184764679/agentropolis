"""End-to-end economy convergence tests for the P3 playable path."""

import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from agentropolis.models import Base, GameState, HousekeepingLog, Inventory, Resource
from agentropolis.services.agent_svc import register_agent
from agentropolis.services.company_svc import get_agent_company, register_company
from agentropolis.services.game_engine import run_housekeeping_sweep
from agentropolis.services.leaderboard import get_leaderboard
from agentropolis.services.market_engine import (
    get_my_orders,
    get_recent_trades,
    place_buy_order,
    place_sell_order,
)
from agentropolis.services.production import (
    get_company_buildings,
    get_recipes,
    settle_all_buildings,
    start_production,
)
from agentropolis.services.seed import seed_game_data
from agentropolis.services.seed_world import seed_world


async def _run_seeded_session(callback):
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with session_factory() as session:
            await seed_game_data(session)
            await seed_world(session)
            result = await callback(session)
            await session.commit()
            return result
    finally:
        await engine.dispose()


def test_agent_company_production_market_path() -> None:
    async def scenario(session: AsyncSession) -> None:
        seller_agent = await register_agent(session, "Seller Agent", None)
        buyer_agent = await register_agent(session, "Buyer Agent", None)

        seller_company = await register_company(
            session,
            "Seller Works",
            founder_agent_id=seller_agent["agent_id"],
        )
        buyer_company = await register_company(
            session,
            "Buyer Forge",
            founder_agent_id=buyer_agent["agent_id"],
        )

        seller_status = await get_agent_company(session, seller_agent["agent_id"])
        assert seller_status["company_id"] == seller_company["company_id"]

        buildings = await get_company_buildings(session, seller_company["company_id"])
        extractor = next(
            building for building in buildings if building["building_type"] == "extractor"
        )
        recipes = await get_recipes(session)
        water_recipe = next(recipe for recipe in recipes if recipe["name"] == "Extract Water")

        inventory_before = await session.execute(
            select(Inventory.quantity)
            .join(Resource, Resource.id == Inventory.resource_id)
            .where(
                Inventory.company_id == seller_company["company_id"],
                Inventory.region_id == seller_company["region_id"],
                Resource.ticker == "H2O",
            )
        )
        h2o_before = float(inventory_before.scalar_one())

        started_at = datetime.now(UTC)
        await start_production(
            session,
            seller_company["company_id"],
            extractor["building_id"],
            water_recipe["recipe_id"],
        )
        production_summary = await settle_all_buildings(
            session,
            started_at + timedelta(seconds=61),
        )
        assert production_summary["cycles_completed"] >= 1

        inventory_after = await session.execute(
            select(Inventory.quantity)
            .join(Resource, Resource.id == Inventory.resource_id)
            .where(
                Inventory.company_id == seller_company["company_id"],
                Inventory.region_id == seller_company["region_id"],
                Resource.ticker == "H2O",
            )
        )
        h2o_after = float(inventory_after.scalar_one())
        assert h2o_after > h2o_before

        buy_order_id = await place_buy_order(session, buyer_company["company_id"], "H2O", 5, 7.5)
        sell_order_id = await place_sell_order(session, seller_company["company_id"], "H2O", 5, 7.0)
        assert buy_order_id > 0
        assert sell_order_id > 0

        buyer_orders = await get_my_orders(session, buyer_company["company_id"], status="ALL")
        seller_orders = await get_my_orders(session, seller_company["company_id"], status="ALL")
        assert buyer_orders[0]["status"] == "FILLED"
        assert seller_orders[0]["status"] == "FILLED"

        trades = await get_recent_trades(session, resource_ticker="H2O", ticks=5)
        assert len(trades) == 1
        assert trades[0]["resource"] == "H2O"

        leaderboard = await get_leaderboard(session)
        assert {entry["company_name"] for entry in leaderboard} == {"Seller Works", "Buyer Forge"}

    asyncio.run(_run_seeded_session(scenario))


def test_housekeeping_cycle_updates_game_state_and_log() -> None:
    async def scenario(session: AsyncSession) -> None:
        agent = await register_agent(session, "Housekeeping Agent", None)
        company = await register_company(
            session,
            "Housekeeping Works",
            founder_agent_id=agent["agent_id"],
        )

        summary = await run_housekeeping_sweep(session)
        assert summary["current_tick"] == 1
        assert "production" in summary
        assert "trade" in summary
        assert "consumption" in summary

        state = await session.get(GameState, 1)
        assert state is not None
        assert state.current_tick == 1
        assert state.is_running is True
        assert state.total_currency_supply >= 0
        assert state.inflation_index > 0

        log_result = await session.execute(
            select(HousekeepingLog).order_by(HousekeepingLog.id.desc()).limit(1)
        )
        housekeeping_log = log_result.scalar_one()
        assert housekeeping_log.sweep_count == 1
        assert housekeeping_log.active_companies >= 1
        assert housekeeping_log.production_summary is not None
        assert housekeeping_log.analytics_summary is not None
        assert company["company_id"] > 0

    asyncio.run(_run_seeded_session(scenario))
