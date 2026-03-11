"""Preview-surface tests for strategy, decisions, and warfare."""

import asyncio
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from agentropolis.main import app
from agentropolis.models import Agent, Base, Building, BuildingType, Company, Region
from agentropolis.models.decision_log import DecisionType
from agentropolis.services.agent_svc import register_agent
from agentropolis.services.decision_log_svc import (
    get_decision_analysis,
    get_recent_decisions,
    record_decision,
)
from agentropolis.services.seed import seed_game_data
from agentropolis.services.seed_world import seed_world
from agentropolis.services.strategy_svc import (
    create_or_update_profile,
    get_profile,
    get_public_profile,
)
from agentropolis.services.warfare_svc import (
    activate_contract,
    cancel_contract,
    create_contract,
    enlist_in_contract,
    get_contract,
    get_region_threats,
    list_contracts,
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


def test_strategy_profile_and_decision_journal_services() -> None:
    async def scenario(session: AsyncSession) -> None:
        created = await register_agent(session, "Tactician", None)
        agent_id = created["agent_id"]

        updated = await create_or_update_profile(
            session,
            agent_id,
            combat_doctrine="DEFENSIVE",
            risk_tolerance=0.2,
            primary_focus="LEADERSHIP",
            secondary_focus="COMMERCE",
            default_stance="OPEN",
            standing_orders={"buy_if": {"ORE": {"below": 10}}},
        )
        assert updated["combat_doctrine"] == "DEFENSIVE"
        assert updated["primary_focus"] == "LEADERSHIP"

        profile = await get_profile(session, agent_id)
        assert profile is not None
        public_profile = await get_public_profile(session, agent_id)
        assert public_profile is not None
        assert "risk_tolerance" not in public_profile
        assert public_profile["standing_orders"]["buy_if"]["ORE"]["below"] == 10

        trade_entry = await record_decision(
            session,
            agent_id,
            DecisionType.TRADE,
            "Bought ORE",
            amount_copper=100,
        )
        trade_entry.resolved_at = datetime.now(UTC)
        trade_entry.profit_copper = 30
        trade_entry.is_profitable = True
        trade_entry.quality_score = 65.0

        travel_entry = await record_decision(
            session,
            agent_id,
            DecisionType.TRAVEL,
            "Moved regions",
            amount_copper=0,
        )
        travel_entry.resolved_at = datetime.now(UTC)
        travel_entry.profit_copper = 0
        travel_entry.is_profitable = None

        recent = await get_recent_decisions(session, agent_id)
        assert len(recent) == 2

        analysis = await get_decision_analysis(session, agent_id)
        assert analysis["overall"]["total_decisions"] == 2
        assert analysis["by_type"]["TRADE"]["wins"] == 1
        assert analysis["by_type"]["TRADE"]["total_profit_copper"] == 30

    asyncio.run(_run_seeded_session(scenario))


def test_warfare_contract_lifecycle_and_region_threats() -> None:
    async def scenario(session: AsyncSession) -> None:
        employer = await register_agent(session, "Employer", None)
        mercenary = await register_agent(session, "Mercenary", None)

        employer_agent = await session.get(Agent, employer["agent_id"])
        assert employer_agent is not None
        employer_agent.personal_balance = 10_000

        frontier_gate = (
            await session.execute(
                select(Region).where(Region.name == "Frontier Gate")
            )
        ).scalar_one()
        building_type = (
            await session.execute(
                select(BuildingType).where(BuildingType.name == "warehouse")
            )
        ).scalar_one()

        company = Company(
            name="Frontier Works",
            founder_agent_id=employer["agent_id"],
            region_id=frontier_gate.id,
            balance=1_000,
            net_worth=1_000,
        )
        session.add(company)
        await session.flush()

        building = Building(
            company_id=company.id,
            agent_id=employer["agent_id"],
            region_id=frontier_gate.id,
            building_type_id=building_type.id,
        )
        session.add(building)
        await session.flush()

        created = await create_contract(
            session,
            employer["agent_id"],
            "sabotage_building",
            frontier_gate.id,
            250,
            1,
            target_building_id=building.id,
        )
        assert created["status"] == "open"

        detail = await get_contract(session, created["contract_id"])
        assert detail is not None
        assert detail["employer_agent_id"] == employer["agent_id"]
        assert detail["target_building_id"] == building.id

        listed = await list_contracts(session, region_id=frontier_gate.id)
        assert len(listed) == 1
        assert listed[0]["status"] == "open"

        enlist = await enlist_in_contract(session, mercenary["agent_id"], created["contract_id"])
        assert enlist["status"] == "enlisted"

        activated = await activate_contract(session, created["contract_id"])
        assert activated["status"] == "active"

        threats = await get_region_threats(session, frontier_gate.id)
        assert threats["active_threats"] == 1

        cancelled = await cancel_contract(session, employer["agent_id"], created["contract_id"])
        assert cancelled["status"] == "cancelled"
        assert cancelled["refund"] > 0

        threats_after = await get_region_threats(session, frontier_gate.id)
        assert threats_after["active_threats"] == 0

    asyncio.run(_run_seeded_session(scenario))


def test_training_and_warfare_preview_routes_are_mounted() -> None:
    paths = {route.path for route in app.routes}

    assert "/api/strategy/profile" in paths
    assert "/api/strategy/dashboard" in paths
    assert "/api/agent/decisions" in paths
    assert "/api/warfare/contracts" in paths
    assert "/api/warfare/region/{region_id}/threats" in paths
