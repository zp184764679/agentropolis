"""Regression tests for worker consumption settlement."""

import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from agentropolis.models import Base, Inventory, Resource, Worker
from agentropolis.services.company_svc import register_company
from agentropolis.services.consumption import tick_consumption
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


def test_tick_consumption_recovers_satisfaction_when_supplied() -> None:
    async def scenario(session: AsyncSession) -> None:
        created = await register_company(session, "Recovery Foods")
        worker = (
            await session.execute(select(Worker).where(Worker.company_id == created["company_id"]))
        ).scalar_one()
        worker.satisfaction = 60.0
        await session.flush()

        summary = await tick_consumption(session)

        assert summary["companies_processed"] == 1
        assert summary["total_rat_consumed"] > 0
        assert summary["total_dw_consumed"] > 0

        refreshed = (
            await session.execute(select(Worker).where(Worker.company_id == created["company_id"]))
        ).scalar_one()
        assert float(refreshed.satisfaction) > 60.0

    asyncio.run(_run_seeded_session(scenario))


def test_tick_consumption_decays_satisfaction_and_causes_attrition_when_unsupplied() -> None:
    async def scenario(session: AsyncSession) -> None:
        created = await register_company(session, "Attrition Works")
        worker = (
            await session.execute(select(Worker).where(Worker.company_id == created["company_id"]))
        ).scalar_one()
        worker.satisfaction = 0.0
        worker.count = 100

        result = await session.execute(
            select(Inventory)
            .join(Resource, Inventory.resource_id == Resource.id)
            .where(
                Inventory.company_id == created["company_id"],
                Resource.ticker.in_(("RAT", "DW")),
            )
        )
        for inventory in result.scalars().all():
            inventory.quantity = 0
            inventory.reserved = 0
        await session.flush()

        summary = await tick_consumption(session)

        assert summary["workers_lost"] > 0
        refreshed = (
            await session.execute(select(Worker).where(Worker.company_id == created["company_id"]))
        ).scalar_one()
        assert int(refreshed.count) < 100
        assert float(refreshed.satisfaction) == 0.0

    asyncio.run(_run_seeded_session(scenario))
