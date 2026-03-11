"""Treaty effects and regional infrastructure tests for issues #49 and #50."""

import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from agentropolis.models import (
    Agent,
    Base,
    Building,
    MercenaryContract,
    NpcShop,
    Region,
    RegionConnection,
    RegionalProject,
    Treaty,
)
from agentropolis.services.agent_svc import register_agent
from agentropolis.services.company_svc import register_company
from agentropolis.services.diplomacy_svc import accept_treaty, propose_treaty
from agentropolis.services.market_engine import get_recent_trades, place_buy_order, place_sell_order
from agentropolis.services.production import build_building
from agentropolis.services.regional_project_svc import (
    fund_project,
    get_region_projects,
    propose_project,
    settle_project_completions,
)
from agentropolis.services.seed import seed_game_data
from agentropolis.services.seed_world import seed_world
from agentropolis.services.warfare_svc import create_contract


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


def test_trade_agreement_reduces_market_tax() -> None:
    async def scenario(session: AsyncSession) -> None:
        seller_agent = await register_agent(session, "Treaty Seller", None)
        buyer_agent = await register_agent(session, "Treaty Buyer", None)
        seller_company = await register_company(
            session,
            "Treaty Seller Works",
            founder_agent_id=seller_agent["agent_id"],
        )
        buyer_company = await register_company(
            session,
            "Treaty Buyer Works",
            founder_agent_id=buyer_agent["agent_id"],
        )

        region = await session.get(Region, seller_company["region_id"])
        assert region is not None
        treasury_before = int(region.treasury)

        proposed = await propose_treaty(
            session,
            "trade_agreement",
            party_a_agent_id=seller_agent["agent_id"],
            party_b_agent_id=buyer_agent["agent_id"],
        )
        await accept_treaty(session, proposed["treaty_id"], buyer_agent["agent_id"])

        await place_buy_order(session, buyer_company["company_id"], "RAT", 10, 20.0)
        await place_sell_order(session, seller_company["company_id"], "RAT", 10, 20.0)
        trades = await get_recent_trades(session, resource_ticker="RAT", ticks=5)
        assert len(trades) == 1

        assert int(region.treasury) - treasury_before == 5

    asyncio.run(_run_seeded_session(scenario))


def test_treaty_blocks_warfare_and_mutual_defense_spawns_defense_contracts() -> None:
    async def scenario(session: AsyncSession) -> None:
        attacker = await register_agent(session, "Treaty Attacker", None)
        defender = await register_agent(session, "Treaty Defender", None)
        ally = await register_agent(session, "Treaty Ally", None)
        combat_region = (
            await session.execute(select(Region).where(Region.name == "Iron Vale"))
        ).scalar_one()
        for agent_id in (attacker["agent_id"], defender["agent_id"], ally["agent_id"]):
            agent_model = await session.get(Agent, agent_id)
            assert agent_model is not None
            agent_model.current_region_id = combat_region.id
            agent_model.home_region_id = combat_region.id

        attacker_company = await register_company(
            session,
            "Treaty Attack Co",
            founder_agent_id=attacker["agent_id"],
        )
        defender_company = await register_company(
            session,
            "Treaty Defense Co",
            founder_agent_id=defender["agent_id"],
        )
        assert attacker_company["company_id"] > 0

        defender_build = await build_building(session, defender_company["company_id"], "extractor")

        blocked_treaty = await propose_treaty(
            session,
            "non_aggression",
            party_a_agent_id=attacker["agent_id"],
            party_b_agent_id=defender["agent_id"],
        )
        await accept_treaty(session, blocked_treaty["treaty_id"], defender["agent_id"])

        try:
            await create_contract(
                session,
                attacker["agent_id"],
                "sabotage_building",
                defender_company["region_id"],
                reward_per_agent=200,
                max_agents=2,
                target_building_id=defender_build["building_id"],
            )
        except ValueError as exc:
            assert "blocks warfare" in str(exc)
        else:
            raise AssertionError("Expected treaty-blocked warfare contract to fail")

        mutual = await propose_treaty(
            session,
            "mutual_defense",
            party_a_agent_id=defender["agent_id"],
            party_b_agent_id=ally["agent_id"],
        )
        await accept_treaty(session, mutual["treaty_id"], ally["agent_id"])

        result = await session.execute(select(Treaty).where(Treaty.id == blocked_treaty["treaty_id"]))
        blocked_model = result.scalar_one()
        blocked_model.is_active = False

        created = await create_contract(
            session,
            attacker["agent_id"],
            "sabotage_building",
            defender_company["region_id"],
            reward_per_agent=200,
            max_agents=2,
            target_building_id=defender_build["building_id"],
        )
        assert created["mutual_defense_contracts_created"] == 1

        defense_contract = (
            await session.execute(
                select(MercenaryContract)
                .where(
                    MercenaryContract.employer_agent_id == ally["agent_id"],
                    MercenaryContract.target_building_id == defender_build["building_id"],
                )
                .order_by(MercenaryContract.id.desc())
            )
        ).scalars().first()
        assert defense_contract is not None
        assert defense_contract.mission_type.value == "defend_building"

    asyncio.run(_run_seeded_session(scenario))


def test_regional_projects_apply_world_effects() -> None:
    async def scenario(session: AsyncSession) -> None:
        agent = await register_agent(session, "Project Planner", None)
        region = (
            await session.execute(select(Region).order_by(Region.id.asc()).limit(1))
        ).scalar_one()
        region.treasury = 5_000_000

        road = await propose_project(session, agent["agent_id"], region.id, "road_improvement")
        road_conn = (
            await session.execute(
                select(RegionConnection)
                .where(RegionConnection.from_region_id == region.id)
                .order_by(RegionConnection.id.asc())
                .limit(1)
            )
        ).scalar_one()
        travel_before = int(road_conn.travel_time_seconds)
        await fund_project(session, road["project_id"], copper_amount=road["copper_cost"])
        road_project = (
            await session.execute(select(RegionalProject).where(RegionalProject.id == road["project_id"]))
        ).scalar_one()
        road_summary = await settle_project_completions(
            session,
            now=road_project.started_at + timedelta(seconds=road_project.duration_seconds + 1),
        )
        assert road_summary["completed_count"] == 1
        assert int(road_conn.travel_time_seconds) < travel_before

        market = await propose_project(session, agent["agent_id"], region.id, "market_expansion")
        tax_before = float(region.tax_rate)
        await fund_project(
            session,
            market["project_id"],
            copper_amount=market["copper_cost"],
            nxc_amount=market["nxc_cost"],
        )
        market_project = (
            await session.execute(select(RegionalProject).where(RegionalProject.id == market["project_id"]))
        ).scalar_one()
        await settle_project_completions(
            session,
            now=market_project.started_at + timedelta(seconds=market_project.duration_seconds + 1),
        )
        assert float(region.tax_rate) < tax_before

        company = await register_company(
            session,
            "Fortification Works",
            founder_agent_id=agent["agent_id"],
        )
        building = await build_building(session, company["company_id"], "extractor")
        fort = await propose_project(session, agent["agent_id"], company["region_id"], "fortification")
        trade_hub = await propose_project(session, agent["agent_id"], company["region_id"], "trade_hub")
        project_rows = await get_region_projects(session, company["region_id"])
        assert len(project_rows) >= 2

        building_model = (
            await session.execute(select(Building).where(Building.id == building["building_id"]))
        ).scalar_one()
        max_before = float(building_model.max_durability)

        await fund_project(
            session,
            fort["project_id"],
            copper_amount=fort["copper_cost"],
            nxc_amount=fort["nxc_cost"],
        )
        fort_project = (
            await session.execute(select(RegionalProject).where(RegionalProject.id == fort["project_id"]))
        ).scalar_one()
        await settle_project_completions(
            session,
            now=fort_project.started_at + timedelta(seconds=fort_project.duration_seconds + 1),
        )
        assert float(building_model.max_durability) > max_before

        await fund_project(
            session,
            trade_hub["project_id"],
            copper_amount=trade_hub["copper_cost"],
            nxc_amount=trade_hub["nxc_cost"],
        )
        trade_hub_project = (
            await session.execute(select(RegionalProject).where(RegionalProject.id == trade_hub["project_id"]))
        ).scalar_one()
        await settle_project_completions(
            session,
            now=trade_hub_project.started_at + timedelta(seconds=trade_hub_project.duration_seconds + 1),
        )
        shops = (
            await session.execute(
                select(NpcShop).where(
                    NpcShop.region_id == company["region_id"],
                    NpcShop.shop_type == "trade_hub",
                )
            )
        ).scalars().all()
        assert len(shops) == 1

    asyncio.run(_run_seeded_session(scenario))
