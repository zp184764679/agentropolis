"""Event effect and building decay tests for issues #43 and #44."""

import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from agentropolis.models import Base, Building, BuildingStatus, Region, WorldEvent
from agentropolis.services.agent_svc import register_agent
from agentropolis.services.company_svc import register_company
from agentropolis.services.event_svc import apply_active_event_effects
from agentropolis.services.game_engine import run_housekeeping_sweep
from agentropolis.services.maintenance_svc import settle_building_decay
from agentropolis.services.production import (
    get_company_buildings,
    get_recipes,
    settle_all_buildings,
    start_production,
)
from agentropolis.services.seed import seed_game_data
from agentropolis.services.seed_world import seed_world
from agentropolis.services.tax_svc import calculate_tax
from agentropolis.services.world_svc import find_path, start_travel


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


def test_event_effects_modify_travel_tax_and_production() -> None:
    async def scenario(session: AsyncSession) -> None:
        founder = await register_agent(session, "Event Founder", None)
        company = await register_company(
            session,
            "Event Works",
            founder_agent_id=founder["agent_id"],
        )

        destination = (
            await session.execute(
                select(Region.id)
                .where(Region.id != founder["current_region_id"])
                .order_by(Region.id.asc())
                .limit(1)
            )
        ).scalar_one()

        session.add(
            WorldEvent(
                event_type="trade_fair",
                region_id=founder["current_region_id"],
                description="Boost trade and travel",
                effects={
                    "production_modifier": 1.5,
                    "travel_time_modifier": 0.5,
                    "tax_modifier": 2.0,
                },
                starts_at=datetime.now(UTC) - timedelta(minutes=5),
                ends_at=datetime.now(UTC) + timedelta(hours=1),
                is_active=True,
            )
        )
        await session.flush()

        effect_summary = await apply_active_event_effects(session, now=datetime.now(UTC))
        assert effect_summary["active_event_count"] == 1
        assert effect_summary["affected_regions"] == 1

        path = await find_path(session, founder["current_region_id"], destination)
        travel = await start_travel(session, founder["agent_id"], destination, now=datetime.now(UTC))
        arrived_at = datetime.fromisoformat(travel["arrives_at"])
        departed_at = datetime.fromisoformat(travel["departed_at"])
        assert int((arrived_at - departed_at).total_seconds()) == int(path["total_time_seconds"] * 0.5)

        assert await calculate_tax(session, founder["current_region_id"], 100) == 10

        buildings = await get_company_buildings(session, company["company_id"])
        extractor = next(
            building for building in buildings if building["building_type"] == "extractor"
        )
        recipes = await get_recipes(session)
        water_recipe = next(recipe for recipe in recipes if recipe["name"] == "Extract Water")

        started_at = datetime.now(UTC)
        await start_production(
            session,
            company["company_id"],
            extractor["building_id"],
            water_recipe["recipe_id"],
        )
        settled = await settle_all_buildings(session, started_at + timedelta(seconds=61))
        assert settled["cycles_completed"] >= 1
        assert settled["outputs"]["H2O"] == 15.0

    asyncio.run(_run_seeded_session(scenario))


def test_building_decay_uses_durability_cursor_and_disables_ruins() -> None:
    async def scenario(session: AsyncSession) -> None:
        founder = await register_agent(session, "Decay Builder", None)
        company = await register_company(
            session,
            "Decay Builders",
            founder_agent_id=founder["agent_id"],
        )

        building = (
            await session.execute(
                select(Building).where(Building.company_id == company["company_id"]).order_by(Building.id.asc())
            )
        ).scalars().first()
        assert building is not None

        building.durability = 2.0
        building.last_durability_at = datetime.now(UTC) - timedelta(hours=10)
        result = await settle_building_decay(session, building.id, now=datetime.now(UTC))
        assert result["old_durability"] == 2.0
        assert result["new_durability"] == 0.0
        assert result["status"] == BuildingStatus.DISABLED.value
        assert building.last_durability_at is not None

    asyncio.run(_run_seeded_session(scenario))


def test_housekeeping_logs_event_and_building_maintenance_summary() -> None:
    async def scenario(session: AsyncSession) -> None:
        founder = await register_agent(session, "Maintenance Event Founder", None)
        company = await register_company(
            session,
            "Maintenance Event Works",
            founder_agent_id=founder["agent_id"],
        )
        building = (
            await session.execute(
                select(Building).where(Building.company_id == company["company_id"]).order_by(Building.id.asc())
            )
        ).scalars().first()
        assert building is not None
        building.last_durability_at = datetime.now(UTC) - timedelta(hours=4)

        session.add(
            WorldEvent(
                event_type="harvest_boom",
                region_id=company["region_id"],
                description="Production spike",
                effects={"production_modifier": 1.1},
                starts_at=datetime.now(UTC) - timedelta(minutes=10),
                ends_at=datetime.now(UTC) + timedelta(hours=1),
                is_active=True,
            )
        )
        await session.flush()

        summary = await run_housekeeping_sweep(session, now=datetime.now(UTC))
        assert summary["analytics"]["event_effects"]["active_event_count"] == 1
        assert summary["admin"]["building_decay"]["buildings_processed"] >= 1

    asyncio.run(_run_seeded_session(scenario))
