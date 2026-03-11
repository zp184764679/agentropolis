"""Regression tests for issues #51 and #52."""

import asyncio
from datetime import UTC, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from agentropolis.models import Base, Building, BuildingType, Company, Recipe
from agentropolis.services.agent_svc import register_agent
from agentropolis.services.company_svc import get_company_workers, register_company
from agentropolis.services.consumption import get_company_workforce_profile
from agentropolis.services.employment_svc import hire_agent
from agentropolis.services.market_engine import (
    get_my_orders,
    get_recent_trades,
    place_buy_order,
    place_sell_order,
)
from agentropolis.services.production import settle_all_buildings, start_production
from agentropolis.services.seed import seed_game_data
from agentropolis.services.seed_world import seed_world
from agentropolis.services.inventory_svc import get_resource_quantity_in_region


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
            return await callback(session)
    finally:
        await engine.dispose()


def test_multi_tier_workforce_changes_consumption_and_output() -> None:
    async def scenario(session: AsyncSession) -> None:
        baseline_founder = await register_agent(session, "Baseline Founder", None)
        managed_founder = await register_agent(session, "Managed Founder", None)
        manager = await register_agent(session, "Managed Manager", None)
        director = await register_agent(session, "Managed Director", None)

        baseline_company = await register_company(
            session,
            "Baseline Workforce Co",
            founder_agent_id=baseline_founder["agent_id"],
        )
        managed_company = await register_company(
            session,
            "Managed Workforce Co",
            founder_agent_id=managed_founder["agent_id"],
        )

        await hire_agent(
            session,
            managed_company["company_id"],
            manager["agent_id"],
            role="manager",
            salary_per_second=2,
        )
        await hire_agent(
            session,
            managed_company["company_id"],
            director["agent_id"],
            role="director",
            salary_per_second=3,
        )

        workforce = await get_company_workers(session, managed_company["company_id"])
        assert workforce["employment_count"] == 2
        assert workforce["tier_counts"]["manager"] == 1
        assert workforce["tier_counts"]["director"] == 1
        assert workforce["management_bonus"] == 0.23
        assert workforce["rat_consumption_per_tick"] == 51.75
        assert round(workforce["dw_consumption_per_tick"], 2) == 31.05
        assert workforce["productivity_modifier"] == 1.23

        baseline_profile = await get_company_workforce_profile(session, baseline_company["company_id"])
        assert baseline_profile["productivity_modifier"] == 1.0

        extractor_type = (
            await session.execute(select(BuildingType).where(BuildingType.name == "extractor"))
        ).scalar_one()
        recipe = (
            await session.execute(select(Recipe).where(Recipe.name == "Mine Iron Ore"))
        ).scalar_one()

        baseline_building = (
            await session.execute(
                select(Building)
                .where(
                    Building.company_id == baseline_company["company_id"],
                    Building.building_type_id == extractor_type.id,
                )
                .order_by(Building.id.asc())
            )
        ).scalar_one()
        managed_building = (
            await session.execute(
                select(Building)
                .where(
                    Building.company_id == managed_company["company_id"],
                    Building.building_type_id == extractor_type.id,
                )
                .order_by(Building.id.asc())
            )
        ).scalar_one()

        await start_production(session, baseline_company["company_id"], baseline_building.id, recipe.id)
        await start_production(session, managed_company["company_id"], managed_building.id, recipe.id)

        summary = await settle_all_buildings(
            session,
            now=baseline_building.last_production_at.replace(tzinfo=UTC) + timedelta(seconds=61),
        )
        assert summary["cycles_completed"] >= 2

        baseline_ore = await get_resource_quantity_in_region(
            session,
            baseline_company["company_id"],
            "ORE",
            region_id=baseline_company["region_id"],
        )
        managed_ore = await get_resource_quantity_in_region(
            session,
            managed_company["company_id"],
            "ORE",
            region_id=managed_company["region_id"],
        )
        assert round(float(baseline_ore["quantity"]), 2) == 8.0
        assert round(float(managed_ore["quantity"]), 2) == 9.84
        assert float(managed_ore["quantity"]) > float(baseline_ore["quantity"])

    asyncio.run(_run_seeded_session(scenario))


def test_ioc_orders_cancel_remainder_after_partial_fill() -> None:
    async def scenario(session: AsyncSession) -> None:
        seller = await register_agent(session, "IOC Seller", None)
        buyer = await register_agent(session, "IOC Buyer", None)
        seller_company = await register_company(
            session,
            "IOC Seller Co",
            founder_agent_id=seller["agent_id"],
        )
        buyer_company = await register_company(
            session,
            "IOC Buyer Co",
            founder_agent_id=buyer["agent_id"],
        )

        buyer_model = await session.get(Company, buyer_company["company_id"])
        assert buyer_model is not None
        buyer_balance_before = float(buyer_model.balance)

        await place_sell_order(session, seller_company["company_id"], "RAT", 5, 20.0)
        buyer_order_id = await place_buy_order(
            session,
            buyer_company["company_id"],
            "RAT",
            10,
            25.0,
            "IOC",
        )

        buyer_orders = await get_my_orders(session, buyer_company["company_id"], status="ALL")
        buyer_order = next(order for order in buyer_orders if order["order_id"] == buyer_order_id)
        assert buyer_order["time_in_force"] == "IOC"
        assert buyer_order["status"] == "CANCELLED"
        assert float(buyer_order["remaining"]) == 0.0

        seller_orders = await get_my_orders(session, seller_company["company_id"], status="ALL")
        assert seller_orders[0]["status"] == "FILLED"

        trades = await get_recent_trades(session, resource_ticker="RAT", ticks=5)
        assert len(trades) == 1
        assert float(trades[0]["quantity"]) == 5.0
        assert float(trades[0]["price"]) == 20.0

        assert float(buyer_model.balance) == buyer_balance_before - 100.0

    asyncio.run(_run_seeded_session(scenario))
