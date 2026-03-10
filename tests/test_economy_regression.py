"""Economy regression scenarios anchored to governance thresholds."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from agentropolis.models import Base, Company, GameState, HousekeepingLog
from agentropolis.services.agent_svc import register_agent
from agentropolis.services.company_svc import register_company
from agentropolis.services.economy_governance import build_governance_snapshot
from agentropolis.services.game_engine import run_housekeeping_sweep
from agentropolis.services.market_engine import get_my_orders, place_buy_order, place_sell_order
from agentropolis.services.production import get_company_buildings, get_recipes, settle_all_buildings, start_production
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
            result = await callback(session)
            await session.commit()
            return result
    finally:
        await engine.dispose()


def test_governance_regression_catalog_matches_executable_scenarios() -> None:
    snapshot = build_governance_snapshot()
    root = Path(__file__).resolve().parents[1]
    scenario_ids = {scenario["scenario_id"] for scenario in snapshot["regression_scenarios"]}

    assert {
        "production_trade_cycle",
        "worker_starvation_recovery",
        "autonomy_budget_market_guardrails",
        "housekeeping_currency_supply",
    }.issubset(scenario_ids)

    for scenario in snapshot["regression_scenarios"]:
        for test_ref in scenario["tests"]:
            file_path = test_ref.split("::", 1)[0]
            assert (root / file_path).exists(), f"Missing regression test target: {test_ref}"


def test_economy_regression_production_trade_path_stays_within_governance_thresholds() -> None:
    thresholds = build_governance_snapshot()["thresholds"]

    async def scenario(session: AsyncSession) -> None:
        seller_agent = await register_agent(session, "Regression Seller", None)
        buyer_agent = await register_agent(session, "Regression Buyer", None)

        seller_company = await register_company(
            session,
            "Regression Seller Works",
            founder_agent_id=seller_agent["agent_id"],
        )
        buyer_company = await register_company(
            session,
            "Regression Buyer Works",
            founder_agent_id=buyer_agent["agent_id"],
        )

        buildings = await get_company_buildings(session, seller_company["company_id"])
        extractor = next(
            building for building in buildings if building["building_type"] == "extractor"
        )
        recipe = next(recipe for recipe in await get_recipes(session) if recipe["name"] == "Extract Water")
        started_at = datetime.now(UTC)
        await start_production(
            session,
            seller_company["company_id"],
            extractor["building_id"],
            recipe["recipe_id"],
        )
        production_summary = await settle_all_buildings(session, started_at + timedelta(seconds=61))
        assert production_summary["cycles_completed"] >= 1

        await place_buy_order(session, buyer_company["company_id"], "H2O", 5, 7.5)
        await place_sell_order(session, seller_company["company_id"], "H2O", 5, 7.0)
        sweep = await run_housekeeping_sweep(session, tick_number=1, now=datetime.now(UTC))

        state = await session.get(GameState, 1)
        assert state is not None
        assert float(state.inflation_index) < float(thresholds["inflation_index"]["critical_above"])
        assert int(state.total_currency_supply) >= 0
        assert sweep["error_count"] == 0

        orders = await get_my_orders(session, buyer_company["company_id"], status="ALL")
        assert any(order["status"] in {"FILLED", "PARTIALLY_FILLED"} for order in orders)

        companies = (
            await session.execute(select(Company).where(Company.id.in_((seller_company["company_id"], buyer_company["company_id"]))))
        ).scalars().all()
        assert all(float(company.balance) >= 0 for company in companies)

        latest_log = (
            await session.execute(
                select(HousekeepingLog).order_by(HousekeepingLog.id.desc()).limit(1)
            )
        ).scalar_one()
        assert latest_log.error_count == 0

    asyncio.run(_run_seeded_session(scenario))
