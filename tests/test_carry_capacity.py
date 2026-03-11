"""Carry capacity regression test for issue #48."""

import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from agentropolis.models import AgentSkill, Base, Inventory, Region
from agentropolis.services.agent_svc import register_agent
from agentropolis.services.seed import seed_game_data
from agentropolis.services.seed_world import seed_world
from agentropolis.services.world_svc import calculate_carry_capacity, start_travel


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


def test_travel_respects_carry_capacity_and_strength_bonus() -> None:
    async def scenario(session: AsyncSession) -> None:
        agent = await register_agent(session, "Carry Scout", None)
        destination = (
            await session.execute(
                select(Region.id)
                .where(Region.id != agent["current_region_id"])
                .order_by(Region.id.asc())
                .limit(1)
            )
        ).scalar_one()

        inventory_rows = (
            await session.execute(select(Inventory).where(Inventory.agent_id == agent["agent_id"]))
        ).scalars().all()
        assert inventory_rows
        for row in inventory_rows:
            row.quantity = 40

        try:
            await start_travel(session, agent["agent_id"], destination)
        except ValueError as exc:
            assert "carry capacity" in str(exc)
        else:
            raise AssertionError("Expected overweight travel to fail")

        session.add(AgentSkill(agent_id=agent["agent_id"], skill_name="Strength", level=4, xp=0))
        await session.flush()

        assert calculate_carry_capacity(4) == 90
        travel = await start_travel(session, agent["agent_id"], destination)
        assert travel["to_region_id"] == destination

    asyncio.run(_run_seeded_session(scenario))
