"""Employment and wage settlement tests for issue #39."""

import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from agentropolis.models import Agent, AgentEmployment, Base, Company
from agentropolis.services.agent_svc import register_agent
from agentropolis.services.company_svc import register_company
from agentropolis.services.employment_svc import (
    fire_agent,
    hire_agent,
    list_employees,
    settle_all_wages,
    settle_wages,
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


def test_hire_settle_fire_flow() -> None:
    async def scenario(session: AsyncSession) -> None:
        founder = await register_agent(session, "Employment Founder", None)
        worker = await register_agent(session, "Employment Worker", None)
        company = await register_company(
            session,
            "Employment Works",
            founder_agent_id=founder["agent_id"],
        )

        hired = await hire_agent(
            session,
            company["company_id"],
            worker["agent_id"],
            role="manager",
            salary_per_second=3,
        )
        assert hired["role"] == "manager"

        employees = await list_employees(session, company["company_id"])
        assert len(employees) == 1
        assert employees[0]["agent_id"] == worker["agent_id"]
        assert employees[0]["salary_per_second"] == 3

        employment = (
            await session.execute(
                select(AgentEmployment).where(AgentEmployment.id == hired["employment_id"])
            )
        ).scalar_one()
        company_model = await session.get(Company, company["company_id"])
        worker_model = await session.get(Agent, worker["agent_id"])
        assert company_model is not None
        assert worker_model is not None

        company_balance_before = float(company_model.balance)
        worker_balance_before = int(worker_model.personal_balance)

        settled = await settle_wages(
            session,
            employment.id,
            now=employment.last_wage_paid_at + timedelta(seconds=10),
        )
        assert settled["wages_paid"] == 30

        assert float(company_model.balance) == company_balance_before - 30
        assert int(worker_model.personal_balance) == worker_balance_before + 30

        fired = await fire_agent(
            session,
            company["company_id"],
            worker["agent_id"],
            now=employment.last_wage_paid_at + timedelta(seconds=10),
        )
        assert fired["wages_settled"] == 30

        remaining = await list_employees(session, company["company_id"])
        assert remaining == []

    asyncio.run(_run_seeded_session(scenario))


def test_duplicate_hire_and_partial_payment() -> None:
    async def scenario(session: AsyncSession) -> None:
        founder = await register_agent(session, "Employment Founder Two", None)
        worker = await register_agent(session, "Employment Worker Two", None)
        company = await register_company(
            session,
            "Employment Foundry",
            founder_agent_id=founder["agent_id"],
        )

        hired = await hire_agent(
            session,
            company["company_id"],
            worker["agent_id"],
            salary_per_second=10,
        )

        try:
            await hire_agent(
                session,
                company["company_id"],
                worker["agent_id"],
                salary_per_second=10,
            )
        except ValueError as exc:
            assert "already employed" in str(exc)
        else:
            raise AssertionError("Expected duplicate employment to fail")

        company_model = await session.get(Company, company["company_id"])
        worker_model = await session.get(Agent, worker["agent_id"])
        assert company_model is not None
        assert worker_model is not None

        company_model.balance = 25
        worker_balance_before = int(worker_model.personal_balance)

        employment = (
            await session.execute(
                select(AgentEmployment).where(AgentEmployment.id == hired["employment_id"])
            )
        ).scalar_one()
        settled = await settle_wages(
            session,
            employment.id,
            now=employment.last_wage_paid_at + timedelta(seconds=10),
        )
        assert settled["wages_paid"] == 25
        assert float(company_model.balance) == 0.0
        assert int(worker_model.personal_balance) == worker_balance_before + 25

    asyncio.run(_run_seeded_session(scenario))


def test_settle_all_wages_only_processes_active_companies() -> None:
    async def scenario(session: AsyncSession) -> None:
        founder_one = await register_agent(session, "Employment Founder Three", None)
        founder_two = await register_agent(session, "Employment Founder Four", None)
        worker_one = await register_agent(session, "Employment Worker Three", None)
        worker_two = await register_agent(session, "Employment Worker Four", None)

        active_company = await register_company(
            session,
            "Employment Active Co",
            founder_agent_id=founder_one["agent_id"],
        )
        inactive_company = await register_company(
            session,
            "Employment Inactive Co",
            founder_agent_id=founder_two["agent_id"],
        )

        first = await hire_agent(
            session,
            active_company["company_id"],
            worker_one["agent_id"],
            salary_per_second=2,
        )
        second = await hire_agent(
            session,
            inactive_company["company_id"],
            worker_two["agent_id"],
            salary_per_second=4,
        )

        active_model = await session.get(Company, active_company["company_id"])
        inactive_model = await session.get(Company, inactive_company["company_id"])
        assert active_model is not None
        assert inactive_model is not None
        inactive_model.is_active = False

        active_employment = (
            await session.execute(
                select(AgentEmployment).where(AgentEmployment.id == first["employment_id"])
            )
        ).scalar_one()
        inactive_employment = (
            await session.execute(
                select(AgentEmployment).where(AgentEmployment.id == second["employment_id"])
            )
        ).scalar_one()
        now = max(
            active_employment.last_wage_paid_at,
            inactive_employment.last_wage_paid_at,
        ) + timedelta(seconds=5)

        summary = await settle_all_wages(session, now=now)
        assert summary["employments_processed"] == 1
        assert summary["total_wages_paid"] == 10

    asyncio.run(_run_seeded_session(scenario))
