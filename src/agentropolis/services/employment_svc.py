"""Employment & Wages service - agent employment and salary settlement.

Agents can be hired by companies. Salary is paid lazily from company balance
to agent personal_balance, settled on demand or during housekeeping.
"""

import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentropolis.config import settings
from agentropolis.models.agent import Agent
from agentropolis.models.agent_employment import AgentEmployment, EmploymentRole
from agentropolis.models.company import Company

logger = logging.getLogger(__name__)


async def hire_agent(
    session: AsyncSession,
    company_id: int,
    agent_id: int,
    role: str = "worker",
    salary_per_second: int | None = None,
) -> dict:
    """Hire an agent to work for a company.

    Returns: {"employment_id", "agent_id", "company_id", "role", "salary_per_second"}
    Raises: ValueError if agent already employed at this company or company inactive
    """
    if salary_per_second is None:
        salary_per_second = settings.EMPLOYMENT_DEFAULT_SALARY_PER_SECOND

    # Check company exists and is active
    result = await session.execute(
        select(Company).where(Company.id == company_id, Company.is_active == True)  # noqa: E712
    )
    company = result.scalar_one_or_none()
    if company is None:
        raise ValueError(f"Company {company_id} not found or inactive")

    # Check agent exists and is alive
    result = await session.execute(
        select(Agent).where(Agent.id == agent_id, Agent.is_alive == True)  # noqa: E712
    )
    agent = result.scalar_one_or_none()
    if agent is None:
        raise ValueError(f"Agent {agent_id} not found or dead")

    # Check not already employed
    result = await session.execute(
        select(AgentEmployment).where(
            AgentEmployment.agent_id == agent_id,
            AgentEmployment.company_id == company_id,
        )
    )
    if result.scalar_one_or_none() is not None:
        raise ValueError(f"Agent {agent_id} already employed at company {company_id}")

    try:
        employment_role = EmploymentRole(role)
    except ValueError as err:
        raise ValueError(f"Invalid role: {role}") from err

    now = datetime.now(UTC)
    employment = AgentEmployment(
        agent_id=agent_id,
        company_id=company_id,
        role=employment_role,
        salary_per_second=salary_per_second,
        last_wage_paid_at=now,
    )
    session.add(employment)
    await session.flush()

    return {
        "employment_id": employment.id,
        "agent_id": agent_id,
        "company_id": company_id,
        "role": role,
        "salary_per_second": salary_per_second,
    }


async def fire_agent(
    session: AsyncSession,
    company_id: int,
    agent_id: int,
    now: datetime | None = None,
) -> dict:
    """Fire an agent. Settles outstanding wages first.

    Returns: {"employment_id", "wages_settled", "agent_id"}
    """
    if now is None:
        now = datetime.now(UTC)

    result = await session.execute(
        select(AgentEmployment)
        .where(
            AgentEmployment.agent_id == agent_id,
            AgentEmployment.company_id == company_id,
        )
        .with_for_update()
    )
    employment = result.scalar_one_or_none()
    if employment is None:
        raise ValueError(f"Agent {agent_id} not employed at company {company_id}")

    # Settle outstanding wages before firing
    wage_result = await settle_wages(session, employment.id, now=now)

    eid = employment.id
    await session.delete(employment)
    await session.flush()

    return {
        "employment_id": eid,
        "wages_settled": wage_result["wages_paid"],
        "agent_id": agent_id,
    }


async def settle_wages(
    session: AsyncSession,
    employment_id: int,
    now: datetime | None = None,
) -> dict:
    """Settle wages for a single employment. Lazy settlement pattern.

    Transfers salary from company.balance to agent.personal_balance.
    Returns: {"employment_id", "wages_paid", "elapsed_seconds"}
    """
    if now is None:
        now = datetime.now(UTC)

    result = await session.execute(
        select(AgentEmployment).where(AgentEmployment.id == employment_id).with_for_update()
    )
    employment = result.scalar_one_or_none()
    if employment is None:
        raise ValueError(f"Employment {employment_id} not found")

    # Compute elapsed
    if employment.last_wage_paid_at is None:
        elapsed = 0.0
    else:
        elapsed = (now - employment.last_wage_paid_at).total_seconds()

    if elapsed <= 0 or employment.salary_per_second <= 0:
        return {"employment_id": employment_id, "wages_paid": 0, "elapsed_seconds": 0.0}

    wages_owed = int(employment.salary_per_second * elapsed)
    if wages_owed <= 0:
        return {"employment_id": employment_id, "wages_paid": 0, "elapsed_seconds": elapsed}

    # Load company with lock
    result = await session.execute(
        select(Company).where(Company.id == employment.company_id).with_for_update()
    )
    company = result.scalar_one()

    # Pay what we can afford
    wages_paid = min(wages_owed, company.available_balance)

    if wages_paid > 0:
        company.balance -= wages_paid

        # Credit agent
        result = await session.execute(
            select(Agent).where(Agent.id == employment.agent_id).with_for_update()
        )
        agent = result.scalar_one()
        agent.personal_balance += wages_paid

    employment.last_wage_paid_at = now
    await session.flush()

    return {
        "employment_id": employment_id,
        "wages_paid": wages_paid,
        "elapsed_seconds": elapsed,
    }


async def settle_all_wages(
    session: AsyncSession,
    now: datetime | None = None,
) -> dict:
    """Settle wages for all active employments. Used by housekeeping.

    Returns: {"employments_processed", "total_wages_paid"}
    """
    if now is None:
        now = datetime.now(UTC)

    result = await session.execute(
        select(AgentEmployment.id).join(Company).where(Company.is_active == True)  # noqa: E712
    )
    employment_ids = list(result.scalars().all())

    total_wages = 0
    processed = 0

    for eid in employment_ids:
        try:
            r = await settle_wages(session, eid, now=now)
            total_wages += r["wages_paid"]
            processed += 1
        except Exception:
            logger.exception("Failed to settle wages for employment %d", eid)

    return {
        "employments_processed": processed,
        "total_wages_paid": total_wages,
    }


async def list_employees(
    session: AsyncSession,
    company_id: int,
) -> list[dict]:
    """List all employees of a company.

    Returns: [{"employment_id", "agent_id", "role", "salary_per_second", "hired_at"}]
    """
    result = await session.execute(
        select(AgentEmployment).where(AgentEmployment.company_id == company_id)
    )
    employments = result.scalars().all()

    return [
        {
            "employment_id": e.id,
            "agent_id": e.agent_id,
            "company_id": e.company_id,
            "role": e.role.value,
            "salary_per_second": e.salary_per_second,
            "hired_at": e.hired_at.isoformat(),
            "last_wage_paid_at": e.last_wage_paid_at.isoformat() if e.last_wage_paid_at else None,
        }
        for e in employments
    ]
