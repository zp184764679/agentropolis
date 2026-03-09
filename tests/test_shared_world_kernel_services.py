"""Service-level regression tests for #24/#25/#26/#27."""

import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from agentropolis.api.auth import hash_api_key
from agentropolis.models import Agent, Base, Inventory, Region, Resource, StrategyProfile
from agentropolis.services.agent_svc import (
    eat,
    get_agent_status,
    register_agent,
    respawn,
    rest,
    drink,
)
from agentropolis.services.seed import seed_game_data
from agentropolis.services.seed_world import seed_world
from agentropolis.services.skill_svc import award_xp, get_skill_efficiency
from agentropolis.services.transport_svc import (
    create_transport,
    get_my_transports,
    get_transport_status,
    settle_transport_arrivals,
)
from agentropolis.services.world_svc import (
    find_path,
    get_travel_status,
    settle_travel_arrivals,
    start_travel,
)


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


def test_register_agent_creates_auth_profile_and_starter_inventory() -> None:
    async def scenario(session: AsyncSession) -> None:
        created = await register_agent(session, "Scout One", None)

        agent = await session.get(Agent, created["agent_id"])
        assert agent is not None
        assert agent.api_key_hash == hash_api_key(created["api_key"])
        assert agent.current_region_id == agent.home_region_id
        assert int(agent.personal_balance) == created["balance"]

        profile_result = await session.execute(
            select(StrategyProfile).where(StrategyProfile.agent_id == agent.id)
        )
        assert profile_result.scalar_one_or_none() is not None

        inventory_result = await session.execute(
            select(Resource.ticker, Inventory.quantity)
            .join(Inventory, Inventory.resource_id == Resource.id)
            .where(Inventory.agent_id == agent.id)
        )
        inventory_by_ticker = {
            ticker: float(quantity)
            for ticker, quantity in inventory_result.all()
        }
        assert inventory_by_ticker["RAT"] == 8.0
        assert inventory_by_ticker["DW"] == 8.0

    asyncio.run(_run_seeded_session(scenario))


def test_agent_vitals_actions_and_respawn_flow() -> None:
    async def scenario(session: AsyncSession) -> None:
        created = await register_agent(session, "Scout Two", None)
        agent = await session.get(Agent, created["agent_id"])
        assert agent is not None

        now = datetime.now(UTC)
        agent.hunger = 40.0
        agent.thirst = 45.0
        agent.energy = 35.0
        agent.health = 60.0
        agent.personal_balance = 1000
        agent.last_vitals_at = now - timedelta(hours=2)

        settled = await get_agent_status(session, agent.id, now)
        assert settled["hunger"] < 40.0
        assert settled["thirst"] < 45.0
        assert settled["energy"] < 35.0

        ate = await eat(session, agent.id, amount=1)
        drank = await drink(session, agent.id, amount=1)
        rested = await rest(session, agent.id)

        assert ate["status"]["hunger"] > settled["hunger"]
        assert drank["status"]["thirst"] > settled["thirst"]
        assert rested["energy"] > settled["energy"]

        agent.health = 0.0
        agent.is_alive = False
        agent.is_active = False

        respawned = await respawn(session, agent.id)
        assert respawned["is_alive"] is True
        assert respawned["current_region_id"] == respawned["home_region_id"]
        assert respawned["balance_after"] < respawned["balance_before"]

    asyncio.run(_run_seeded_session(scenario))


def test_world_pathfinding_and_travel_arrival_move_agent_inventory() -> None:
    async def scenario(session: AsyncSession) -> None:
        created = await register_agent(session, "Scout Three", None)
        region_result = await session.execute(
            select(Region).where(Region.name.in_(("Nexus Capital", "Greenreach", "Frontier Gate")))
        )
        regions = {region.name: region for region in region_result.scalars().all()}

        path = await find_path(
            session,
            regions["Nexus Capital"].id,
            regions["Frontier Gate"].id,
        )
        assert path["path"] == [
            regions["Nexus Capital"].id,
            regions["Greenreach"].id,
            regions["Frontier Gate"].id,
        ]

        departed_at = datetime.now(UTC)
        travel = await start_travel(
            session,
            created["agent_id"],
            regions["Frontier Gate"].id,
            now=departed_at,
        )
        assert travel["to_region_id"] == regions["Frontier Gate"].id
        assert await get_travel_status(session, created["agent_id"]) is not None

        arrivals = await settle_travel_arrivals(
            session,
            datetime.fromisoformat(travel["arrives_at"]) + timedelta(seconds=1),
        )
        assert arrivals == 1

        agent = await session.get(Agent, created["agent_id"])
        assert agent is not None
        assert agent.current_region_id == regions["Frontier Gate"].id
        assert await get_travel_status(session, created["agent_id"]) is None

        inventory_result = await session.execute(
            select(Inventory.region_id).where(Inventory.agent_id == created["agent_id"])
        )
        assert {
            region_id for (region_id,) in inventory_result.all()
        } == {regions["Frontier Gate"].id}

    asyncio.run(_run_seeded_session(scenario))


def test_skill_progression_and_transport_delivery() -> None:
    async def scenario(session: AsyncSession) -> None:
        created = await register_agent(session, "Scout Four", None)
        region_result = await session.execute(
            select(Region).where(Region.name.in_(("Nexus Capital", "Iron Vale")))
        )
        regions = {region.name: region for region in region_result.scalars().all()}

        skill_update = await award_xp(session, created["agent_id"], "Trading", 100)
        assert skill_update["new_level"] >= 2
        assert skill_update["leveled_up"] is True
        assert await get_skill_efficiency(session, created["agent_id"], "Trading") > 1.0

        transport = await create_transport(
            session,
            regions["Nexus Capital"].id,
            regions["Iron Vale"].id,
            {"RAT": 2},
            agent_id=created["agent_id"],
        )
        status = await get_transport_status(session, transport["transport_id"])
        assert status["status"] == "in_transit"

        delivered = await settle_transport_arrivals(
            session,
            datetime.fromisoformat(transport["arrives_at"]) + timedelta(seconds=1),
        )
        assert delivered == 1

        delivered_status = await get_transport_status(session, transport["transport_id"])
        assert delivered_status["status"] == "delivered"
        assert len(await get_my_transports(session, agent_id=created["agent_id"])) == 1

        inventory_result = await session.execute(
            select(Resource.ticker, Inventory.region_id, Inventory.quantity)
            .join(Inventory, Inventory.resource_id == Resource.id)
            .where(Inventory.agent_id == created["agent_id"])
        )
        destination_rat = [
            float(quantity)
            for ticker, region_id, quantity in inventory_result.all()
            if ticker == "RAT" and region_id == regions["Iron Vale"].id
        ]
        assert destination_rat == [2.0]

    asyncio.run(_run_seeded_session(scenario))
