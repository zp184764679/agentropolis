"""Regression tests for issues #53, #54, and #55."""

import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from agentropolis.models import Agent, Base, Company, Guild, NpcShop, Region
from agentropolis.services.agent_svc import register_agent
from agentropolis.services.career_svc import set_career
from agentropolis.services.company_svc import register_company
from agentropolis.services.guild_svc import (
    create_guild,
    get_agent_guild_effects,
    join_guild,
    upgrade_guild,
)
from agentropolis.services.inventory_svc import add_resource
from agentropolis.services.market_engine import get_recent_trades, place_buy_order, place_sell_order
from agentropolis.services.npc_shop_svc import get_effective_prices
from agentropolis.services.reputation_svc import adjust_reputation
from agentropolis.services.seed import seed_game_data
from agentropolis.services.seed_world import seed_world
from agentropolis.services.skill_svc import award_xp
from agentropolis.services.storage_svc import get_agent_storage, get_company_storage
from agentropolis.services.production import build_building
from agentropolis.services.warfare_svc import _gather_combat_modifiers


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


def test_guild_levels_apply_storage_tax_and_shop_benefits() -> None:
    async def scenario(session: AsyncSession) -> None:
        leader = await register_agent(session, "Guild Leader", None)
        member = await register_agent(session, "Guild Member", None)
        outsider = await register_agent(session, "Guild Outsider", None)

        home_region = await session.get(Region, leader["current_region_id"])
        assert home_region is not None
        guild = await create_guild(session, leader["agent_id"], "Trade Collective", home_region.id)
        await join_guild(session, member["agent_id"], guild["guild_id"])

        storage_before = await get_agent_storage(session, member["agent_id"], home_region.id)
        assert storage_before["capacity"] == 500

        guild_model = await session.get(Guild, guild["guild_id"])
        assert guild_model is not None
        guild_model.treasury = 10_000_000
        await upgrade_guild(session, leader["agent_id"], guild["guild_id"])
        storage_after_l2 = await get_agent_storage(session, member["agent_id"], home_region.id)
        assert storage_after_l2["capacity"] == 1000

        await upgrade_guild(session, leader["agent_id"], guild["guild_id"])
        await upgrade_guild(session, leader["agent_id"], guild["guild_id"])
        guild_effects = await get_agent_guild_effects(session, member["agent_id"])
        assert guild_effects["tax_reduction"] == 0.05
        assert guild_effects["npc_discount"] == 0.10

        seller_company = await register_company(
            session,
            "Guild Seller Co",
            founder_agent_id=member["agent_id"],
        )
        buyer_company = await register_company(
            session,
            "Guild Buyer Co",
            founder_agent_id=outsider["agent_id"],
        )

        region = await session.get(Region, seller_company["region_id"])
        assert region is not None
        treasury_before = int(region.treasury)

        await place_buy_order(session, buyer_company["company_id"], "RAT", 30, 20.0)
        await place_sell_order(session, seller_company["company_id"], "RAT", 30, 20.0)
        trades = await get_recent_trades(session, resource_ticker="RAT", ticks=5)
        assert len(trades) == 1
        assert int(region.treasury) - treasury_before == 28

        shop = (
            await session.execute(select(NpcShop).where(NpcShop.region_id == home_region.id).limit(1))
        ).scalar_one()
        guild_prices = await get_effective_prices(
            session,
            shop.id,
            reputation=0.0,
            agent_id=member["agent_id"],
        )
        outsider_prices = await get_effective_prices(
            session,
            shop.id,
            reputation=0.0,
            agent_id=outsider["agent_id"],
        )
        assert guild_prices["buy_prices"]["BLD"] < outsider_prices["buy_prices"]["BLD"]

    asyncio.run(_run_seeded_session(scenario))


def test_career_paths_apply_tax_xp_reputation_and_combat_effects() -> None:
    async def scenario(session: AsyncSession) -> None:
        merchant = await register_agent(session, "Career Merchant", None)
        buyer = await register_agent(session, "Career Buyer", None)
        miner = await register_agent(session, "Career Miner", None)
        artisan = await register_agent(session, "Career Artisan", None)
        diplomat = await register_agent(session, "Career Diplomat", None)
        soldier = await register_agent(session, "Career Soldier", None)
        neutral = await register_agent(session, "Career Neutral", None)

        await set_career(session, merchant["agent_id"], "merchant")
        await set_career(session, miner["agent_id"], "miner")
        await set_career(session, artisan["agent_id"], "artisan")
        await set_career(session, diplomat["agent_id"], "diplomat")
        await set_career(session, soldier["agent_id"], "soldier")

        neutral_gatherer = await register_agent(session, "Neutral Gatherer", None)
        neutral_crafter = await register_agent(session, "Neutral Crafter", None)

        mining = await award_xp(session, miner["agent_id"], "Mining", 10)
        neutral_mining = await award_xp(session, neutral_gatherer["agent_id"], "Mining", 10)
        smithing = await award_xp(session, artisan["agent_id"], "Smithing", 10)
        neutral_smithing = await award_xp(session, neutral_crafter["agent_id"], "Smithing", 10)
        assert mining["xp_awarded"] > neutral_mining["xp_awarded"]
        assert smithing["xp_awarded"] > neutral_smithing["xp_awarded"]

        rep = await adjust_reputation(session, diplomat["agent_id"], 10.0)
        assert rep == 15.0

        merchant_company = await register_company(
            session,
            "Career Seller Co",
            founder_agent_id=merchant["agent_id"],
        )
        buyer_company = await register_company(
            session,
            "Career Buyer Co",
            founder_agent_id=buyer["agent_id"],
        )

        region = await session.get(Region, merchant_company["region_id"])
        assert region is not None
        treasury_before = int(region.treasury)
        await place_buy_order(session, buyer_company["company_id"], "RAT", 30, 20.0)
        await place_sell_order(session, merchant_company["company_id"], "RAT", 30, 20.0)
        assert int(region.treasury) - treasury_before == 27

        combat_modifiers = await _gather_combat_modifiers(
            session,
            [soldier["agent_id"], neutral["agent_id"]],
        )
        assert round(combat_modifiers[soldier["agent_id"]]["attack_mult"], 2) == 1.15
        assert round(combat_modifiers[soldier["agent_id"]]["defense_mult"], 2) == 1.15
        assert round(combat_modifiers[neutral["agent_id"]]["attack_mult"], 2) == 1.00

    asyncio.run(_run_seeded_session(scenario))


def test_storage_limits_block_overfill_until_capacity_is_expanded() -> None:
    async def scenario(session: AsyncSession) -> None:
        founder = await register_agent(session, "Storage Founder", None)
        company = await register_company(
            session,
            "Storage Works",
            founder_agent_id=founder["agent_id"],
        )
        await add_resource(
            session,
            company["company_id"],
            "BLD",
            3.0,
            region_id=company["region_id"],
        )

        before = await get_company_storage(session, company["company_id"], company["region_id"])
        await add_resource(
            session,
            company["company_id"],
            "ORE",
            float(before["available"]),
            region_id=company["region_id"],
        )

        try:
            await add_resource(
                session,
                company["company_id"],
                "ORE",
                1.0,
                region_id=company["region_id"],
            )
        except ValueError as exc:
            assert "Storage capacity exceeded" in str(exc)
        else:
            raise AssertionError("Expected storage capacity guard to block overflow")

        await build_building(session, company["company_id"], "warehouse")
        after = await get_company_storage(session, company["company_id"], company["region_id"])
        assert after["capacity"] > before["capacity"]

        updated_quantity = await add_resource(
            session,
            company["company_id"],
            "ORE",
            1.0,
            region_id=company["region_id"],
        )
        assert updated_quantity >= 148.0
        final_storage = await get_company_storage(session, company["company_id"], company["region_id"])
        assert float(final_storage["used"]) == float(after["used"]) + 1.0

    asyncio.run(_run_seeded_session(scenario))
