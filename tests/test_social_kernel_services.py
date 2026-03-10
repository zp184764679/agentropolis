"""Regression tests for guild and diplomacy preview surface."""

import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from agentropolis.main import app
from agentropolis.models import (
    Agent,
    Base,
    Guild,
    GuildMember,
)
from agentropolis.services.agent_svc import register_agent
from agentropolis.services.diplomacy_svc import (
    accept_treaty,
    expire_treaties,
    get_relationships,
    get_treaties,
    propose_treaty,
    set_relationship,
)
from agentropolis.services.guild_svc import (
    collect_maintenance,
    create_guild,
    deposit_to_treasury,
    disband_guild,
    get_guild_info,
    join_guild,
    promote_member,
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


def test_guild_lifecycle_and_maintenance() -> None:
    async def scenario(session: AsyncSession) -> None:
        founder = await register_agent(session, "Guild Founder", None)
        recruit = await register_agent(session, "Guild Recruit", None)

        guild = await create_guild(session, founder["agent_id"], "Iron Banner", founder["home_region_id"])
        assert guild["member_count"] == 1
        assert guild["members"][0]["rank"] == "leader"

        joined = await join_guild(session, recruit["agent_id"], guild["guild_id"])
        assert joined["rank"] == "recruit"

        promoted = await promote_member(
            session,
            founder["agent_id"],
            recruit["agent_id"],
            guild["guild_id"],
            "member",
        )
        assert promoted["new_rank"] == "member"

        treasury = await deposit_to_treasury(
            session,
            founder["agent_id"],
            guild["guild_id"],
            500,
        )
        assert treasury == 500

        guild_state = await get_guild_info(session, guild["guild_id"])
        assert guild_state["member_count"] == 2

        summary = await collect_maintenance(session)
        assert summary["guilds_charged"] == 0
        assert summary["guilds_disbanded"] == 1

        inactive_guild = await session.get(Guild, guild["guild_id"])
        assert inactive_guild is not None
        assert inactive_guild.is_active is False

    asyncio.run(_run_seeded_session(scenario))


def test_guild_disband_returns_treasury_to_leader() -> None:
    async def scenario(session: AsyncSession) -> None:
        founder = await register_agent(session, "Guild Banker", None)
        guild = await create_guild(session, founder["agent_id"], "Coin Ward", founder["home_region_id"])
        treasury = await deposit_to_treasury(session, founder["agent_id"], guild["guild_id"], 800)
        assert treasury == 800

        founder_row_before = await session.get(Agent, founder["agent_id"])
        assert founder_row_before is not None
        balance_before_disband = int(founder_row_before.personal_balance)

        assert await disband_guild(session, founder["agent_id"], guild["guild_id"]) is True

        founder_row_after = await session.get(Agent, founder["agent_id"])
        assert founder_row_after is not None
        assert int(founder_row_after.personal_balance) == balance_before_disband + 800

        members = await session.execute(
            select(GuildMember).where(GuildMember.guild_id == guild["guild_id"])
        )
        assert members.scalars().all() == []

    asyncio.run(_run_seeded_session(scenario))


def test_diplomacy_relationships_and_treaties() -> None:
    async def scenario(session: AsyncSession) -> None:
        alice = await register_agent(session, "Alice Diplomat", None)
        bob = await register_agent(session, "Bob Diplomat", None)

        relationship = await set_relationship(
            session,
            alice["agent_id"],
            bob["agent_id"],
            "friendly",
            trust_delta=15,
        )
        assert relationship["relation_type"] == "friendly"
        assert relationship["trust_score"] == 15

        treaty = await propose_treaty(
            session,
            "alliance",
            party_a_agent_id=alice["agent_id"],
            party_b_agent_id=bob["agent_id"],
            terms={"trade_tax_reduction": 0.05},
            duration_hours=1,
        )
        assert treaty["is_active"] is False

        accepted = await accept_treaty(session, treaty["treaty_id"], bob["agent_id"])
        assert accepted["is_active"] is True

        treaties = await get_treaties(session, agent_id=alice["agent_id"])
        assert len(treaties) == 1
        assert treaties[0]["treaty_type"] == "alliance"

        relationships = await get_relationships(session, alice["agent_id"])
        assert relationships[0]["relation_type"] == "allied"

        expired = await expire_treaties(
            session,
            datetime.now(UTC) + timedelta(hours=2),
        )
        assert expired == 1

        active_treaties = await get_treaties(
            session,
            agent_id=alice["agent_id"],
            active_only=True,
        )
        assert active_treaties == []

    asyncio.run(_run_seeded_session(scenario))


def test_preview_routes_are_mounted_in_main_app() -> None:
    paths = {route.path for route in app.routes}

    assert "/api/agent/register" in paths
    assert "/api/world/map" in paths
    assert "/api/skills/definitions" in paths
    assert "/api/transport/create" in paths
    assert "/api/guild/create" in paths
    assert "/api/diplomacy/treaties" in paths
