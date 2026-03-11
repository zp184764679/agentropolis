"""Player contract lifecycle tests for issue #40."""

import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from agentropolis.config import settings
from agentropolis.models import Agent, Base
from agentropolis.services.agent_svc import register_agent
from agentropolis.services.contract_svc import (
    accept_contract,
    cancel_contract,
    fulfill_contract,
    get_contract,
    list_contracts,
    propose_contract,
)
from agentropolis.services.game_engine import run_housekeeping_sweep
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


def test_contract_propose_accept_fulfill_flow() -> None:
    async def scenario(session: AsyncSession) -> None:
        proposer = await register_agent(session, "Contract Proposer", None)
        acceptor = await register_agent(session, "Contract Acceptor", None)
        proposer_model = await session.get(Agent, proposer["agent_id"])
        acceptor_model = await session.get(Agent, acceptor["agent_id"])
        assert proposer_model is not None
        assert acceptor_model is not None

        proposer_balance_before = int(proposer_model.personal_balance)
        acceptor_balance_before = int(acceptor_model.personal_balance)

        created = await propose_contract(
            session,
            proposer["agent_id"],
            "supply",
            proposer["current_region_id"],
            "Deliver Water",
            {"ticker": "H2O", "quantity": 5},
            escrow_amount=100,
            reward_amount=50,
        )
        assert created["status"] == "proposed"
        assert int(proposer_model.personal_balance) == proposer_balance_before - 150

        accepted = await accept_contract(session, acceptor["agent_id"], created["contract_id"])
        assert accepted["status"] == "accepted"

        fulfilled = await fulfill_contract(session, proposer["agent_id"], created["contract_id"])
        assert fulfilled["status"] == "fulfilled"
        assert fulfilled["reward_paid"] == 150

        detail = await get_contract(session, created["contract_id"])
        assert detail["status"] == "fulfilled"
        assert int(acceptor_model.personal_balance) == acceptor_balance_before + 150
        assert float(acceptor_model.reputation) == settings.REPUTATION_TRADE_BONUS

    asyncio.run(_run_seeded_session(scenario))


def test_cancel_accepted_contract_returns_escrow_and_applies_penalty() -> None:
    async def scenario(session: AsyncSession) -> None:
        proposer = await register_agent(session, "Contract Breaker", None)
        acceptor = await register_agent(session, "Contract Target", None)
        proposer_model = await session.get(Agent, proposer["agent_id"])
        assert proposer_model is not None

        proposer_balance_before = int(proposer_model.personal_balance)

        created = await propose_contract(
            session,
            proposer["agent_id"],
            "purchase",
            proposer["current_region_id"],
            "Buy Rations",
            {"ticker": "RAT", "quantity": 10},
            escrow_amount=60,
            reward_amount=40,
        )
        await accept_contract(session, acceptor["agent_id"], created["contract_id"])

        cancelled = await cancel_contract(session, proposer["agent_id"], created["contract_id"])
        assert cancelled["status"] == "cancelled"
        assert cancelled["escrow_returned"] == 100
        assert int(proposer_model.personal_balance) == proposer_balance_before
        assert float(proposer_model.reputation) == -settings.REPUTATION_CONTRACT_BREACH_PENALTY

    asyncio.run(_run_seeded_session(scenario))


def test_housekeeping_expires_overdue_contracts_and_logs_summary() -> None:
    async def scenario(session: AsyncSession) -> None:
        proposer = await register_agent(session, "Contract Expirer", None)
        acceptor = await register_agent(session, "Contract Expirer Target", None)
        proposer_model = await session.get(Agent, proposer["agent_id"])
        assert proposer_model is not None

        balance_before = int(proposer_model.personal_balance)
        created = await propose_contract(
            session,
            proposer["agent_id"],
            "transport",
            proposer["current_region_id"],
            "Move Ore",
            {"ticker": "ORE", "quantity": 3},
            escrow_amount=75,
            reward_amount=25,
            deadline_seconds=1,
        )
        await accept_contract(session, acceptor["agent_id"], created["contract_id"])
        assert int(proposer_model.personal_balance) == balance_before - 100

        future = datetime.now(UTC) + timedelta(seconds=5)
        summary = await run_housekeeping_sweep(session, now=future)
        detail = await get_contract(session, created["contract_id"])
        listed = await list_contracts(session, status="expired")

        assert detail["status"] == "expired"
        assert listed[0]["contract_id"] == created["contract_id"]
        assert int(proposer_model.personal_balance) == balance_before
        assert summary["admin"]["contracts_expired"]["expired_count"] == 1
        assert summary["admin"]["contracts_expired"]["total_escrow_returned"] == 100

    asyncio.run(_run_seeded_session(scenario))
