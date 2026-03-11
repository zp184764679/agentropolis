"""Regression tests for production and construction flows."""

import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from agentropolis.models import Base, Building, BuildingType, Inventory, Recipe, Resource
from agentropolis.services.company_svc import get_company_status, register_company
from agentropolis.services.inventory_svc import add_resource
from agentropolis.services.production import (
    build_building,
    get_company_buildings,
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
            return await callback(session)
    finally:
        await engine.dispose()


def test_start_and_settle_production_adds_outputs() -> None:
    async def scenario(session: AsyncSession) -> None:
        created = await register_company(session, "Production Hub")
        buildings = await get_company_buildings(session, created["company_id"])
        extractor = next(item for item in buildings if item["building_type"] == "extractor")

        recipe = (
            await session.execute(
                select(Recipe)
                .join(BuildingType, Recipe.building_type_id == BuildingType.id)
                .where(BuildingType.name == "extractor", Recipe.name == "Extract Water")
            )
        ).scalar_one()

        await start_production(
            session,
            created["company_id"],
            extractor["building_id"],
            recipe.id,
        )

        building = await session.get(Building, extractor["building_id"])
        assert building is not None
        building.last_production_at = datetime.now(UTC) - timedelta(seconds=90)
        await session.flush()

        summary = await settle_all_buildings(session, now=datetime.now(UTC))

        assert summary["cycles_completed"] >= 1
        h2o_quantity = (
            await session.execute(
                select(Inventory.quantity)
                .join(Resource, Inventory.resource_id == Resource.id)
                .where(
                    Inventory.company_id == created["company_id"],
                    Resource.ticker == "H2O",
                )
            )
        ).scalar_one()
        assert float(h2o_quantity) >= 110.0

    asyncio.run(_run_seeded_session(scenario))


def test_build_building_deducts_balance_and_materials() -> None:
    async def scenario(session: AsyncSession) -> None:
        created = await register_company(session, "Builder Forge")
        assert isinstance(created["initial_balance"], int)
        await add_resource(session, created["company_id"], "BLD", 10.0, region_id=created["region_id"])
        before = await get_company_status(session, created["company_id"])

        result = await build_building(session, created["company_id"], "warehouse")
        after = await get_company_status(session, created["company_id"])

        assert result["building_type"] == "warehouse"
        assert isinstance(result["cost_credits"], int)
        assert isinstance(before["balance"], int)
        assert isinstance(after["net_worth"], int)
        assert after["balance"] < before["balance"]
        warehouses = [
            item
            for item in await get_company_buildings(session, created["company_id"])
            if item["building_type"] == "warehouse"
        ]
        assert len(warehouses) == 1

    asyncio.run(_run_seeded_session(scenario))
