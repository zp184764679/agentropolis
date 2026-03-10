"""Economy governance and recovery baseline tests."""

from __future__ import annotations

import asyncio

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from agentropolis.models import Base
from agentropolis.services.currency_svc import get_total_currency_supply
from agentropolis.services.economy_governance import build_governance_snapshot
from agentropolis.services.recovery_svc import build_world_snapshot, repair_derived_state
from agentropolis.services.seed import seed_game_data
from agentropolis.services.seed_world import seed_world
from scripts.export_governance_snapshot import build_governance_export


def test_economy_governance_snapshot_has_registry_and_thresholds() -> None:
    snapshot = build_governance_snapshot()

    assert "legacy_workers" in snapshot["registry"]
    assert "agent_vitals" in snapshot["registry"]
    assert "autonomy" in snapshot["registry"]
    assert "rollout_flags" in snapshot["registry"]
    assert "staged_rollout_flags" in snapshot
    assert "ownership_index" in snapshot
    assert snapshot["balance_profile"] == "local_preview_default"
    assert "market_volatility" in snapshot["thresholds"]
    assert "source_sink" in snapshot["thresholds"]
    assert snapshot["staged_rollout_flags"]["ECONOMY_DYNAMIC_PRICING_STAGE"]["value"] == "disabled"
    assert "production_trade_cycle" in {
        item["scenario_id"] for item in snapshot["regression_scenarios"]
    }
    assert snapshot["thresholds"]["inflation_index"]["warning_above"] > 1.0
    assert len(snapshot["review_checklist"]) >= 6
    assert "economy_services" in snapshot["ownership_index"]


def test_governance_export_wraps_snapshot() -> None:
    payload = build_governance_export()
    assert "governance" in payload
    assert payload["governance"]["staged_rollout_flags"]["ECONOMY_BALANCE_PROFILE"]["value"] == (
        "local_preview_default"
    )


def test_recovery_snapshot_and_repair_work_on_seeded_world() -> None:
    async def scenario() -> None:
        engine = create_async_engine(
            "sqlite+aiosqlite:///:memory:",
            echo=False,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with session_factory() as session:
            await seed_game_data(session)
            await seed_world(session)
            await session.commit()

            snapshot = await build_world_snapshot(session)
            repaired = await repair_derived_state(session)
            await session.commit()

            assert snapshot["counts"]["regions"] >= 1
            assert snapshot["counts"]["companies"] == 0
            assert "game_state" in snapshot
            assert repaired["companies_revalued"] == 0
            assert repaired["economy"]["total_currency_supply"] == await get_total_currency_supply(session)

        await engine.dispose()

    asyncio.run(scenario())
