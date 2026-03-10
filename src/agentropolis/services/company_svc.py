"""Company service - registration, balance operations, net worth.

Handles:
- Company registration (generates API key, creates starter buildings/inventory)
- Balance debit/credit with row-level locking
- Net worth recalculation (balance + inventory value + building value)
- Bankruptcy detection (net_worth <= 0 and no assets)
"""

from __future__ import annotations

import secrets
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agentropolis.api.auth import hash_api_key
from agentropolis.config import settings
from agentropolis.models import Agent, Building, BuildingType, Company, Inventory, Region, Resource, Worker
from agentropolis.services.seed import STARTER_BUILDINGS, STARTER_INVENTORY


def _worker_productivity_modifier(satisfaction: float) -> float:
    return 0.5 if satisfaction < settings.LOW_SATISFACTION_THRESHOLD else 1.0


async def _get_company_for_update(session: AsyncSession, company_id: int) -> Company:
    result = await session.execute(
        select(Company).where(Company.id == company_id).with_for_update()
    )
    company = result.scalar_one_or_none()
    if company is None:
        raise ValueError(f"Company {company_id} not found")
    return company


async def _resolve_company_region(
    session: AsyncSession,
    *,
    founder_agent_id: int | None = None,
) -> Region:
    if founder_agent_id is not None:
        founder = (
            await session.execute(select(Agent).where(Agent.id == founder_agent_id))
        ).scalar_one_or_none()
        if founder is None:
            raise ValueError(f"Agent {founder_agent_id} not found")

        region = await session.get(Region, founder.current_region_id)
        if region is not None:
            return region

    result = await session.execute(select(Region).order_by(Region.id.asc()).limit(1))
    region = result.scalar_one_or_none()
    if region is None:
        raise ValueError("No regions available; seed_world() must run before registering companies")
    return region


async def _get_or_create_company_inventory(
    session: AsyncSession,
    *,
    company_id: int,
    region_id: int,
    resource: Resource,
) -> Inventory:
    result = await session.execute(
        select(Inventory)
        .where(
            Inventory.company_id == company_id,
            Inventory.agent_id.is_(None),
            Inventory.region_id == region_id,
            Inventory.resource_id == resource.id,
        )
        .with_for_update()
    )
    inventory = result.scalar_one_or_none()
    if inventory is None:
        inventory = Inventory(
            company_id=company_id,
            agent_id=None,
            region_id=region_id,
            resource_id=resource.id,
            quantity=0,
            reserved=0,
        )
        session.add(inventory)
        await session.flush()
    return inventory


async def register_company(
    session: AsyncSession,
    name: str,
    *,
    founder_agent_id: int | None = None,
) -> dict:
    """Register a new company with starter kit.

    Creates: Company, Worker, starter buildings, starter inventory.
    Returns: {"company_id", "api_key", "name", "balance", "founder_agent_id", "region_id"}
    Raises: ValueError if name already taken or founder already has an active company
    """
    existing = await session.execute(select(Company).where(Company.name == name))
    if existing.scalar_one_or_none() is not None:
        raise ValueError(f"Company name '{name}' is already taken")

    if founder_agent_id is not None:
        founder_result = await session.execute(
            select(Company)
            .where(
                Company.founder_agent_id == founder_agent_id,
                Company.is_active.is_(True),
            )
        )
        if founder_result.scalar_one_or_none() is not None:
            raise ValueError(f"Agent {founder_agent_id} already has an active company")

    region = await _resolve_company_region(session, founder_agent_id=founder_agent_id)
    api_key = secrets.token_hex(settings.API_KEY_LENGTH)
    company = Company(
        name=name,
        api_key_hash=hash_api_key(api_key),
        founder_agent_id=founder_agent_id,
        region_id=region.id,
        balance=float(settings.INITIAL_BALANCE),
        net_worth=float(settings.INITIAL_BALANCE),
        is_active=True,
    )
    session.add(company)
    await session.flush()

    session.add(
        Worker(
            company_id=company.id,
            count=settings.INITIAL_WORKERS,
            satisfaction=100.0,
        )
    )

    building_types_result = await session.execute(
        select(BuildingType).where(BuildingType.name.in_(tuple(STARTER_BUILDINGS)))
    )
    building_types = {
        building_type.name: building_type
        for building_type in building_types_result.scalars().all()
    }
    missing_buildings = sorted(set(STARTER_BUILDINGS) - set(building_types))
    if missing_buildings:
        raise ValueError(f"Missing starter building types: {', '.join(missing_buildings)}")

    for building_name in STARTER_BUILDINGS:
        session.add(
            Building(
                company_id=company.id,
                region_id=region.id,
                building_type_id=building_types[building_name].id,
            )
        )

    resources_result = await session.execute(
        select(Resource).where(Resource.ticker.in_(tuple(STARTER_INVENTORY)))
    )
    resources = {resource.ticker: resource for resource in resources_result.scalars().all()}
    missing_resources = sorted(set(STARTER_INVENTORY) - set(resources))
    if missing_resources:
        raise ValueError(f"Missing starter resources: {', '.join(missing_resources)}")

    for ticker, quantity in STARTER_INVENTORY.items():
        inventory = await _get_or_create_company_inventory(
            session,
            company_id=company.id,
            region_id=region.id,
            resource=resources[ticker],
        )
        inventory.quantity = float(inventory.quantity) + float(quantity)

    await session.flush()
    await recalculate_net_worth(session, company.id)

    return {
        "company_id": company.id,
        "company_name": company.name,
        "founder_agent_id": company.founder_agent_id,
        "region_id": company.region_id,
        "api_key": api_key,
        "initial_balance": float(company.balance),
    }


async def debit_balance(session: AsyncSession, company_id: int, amount: float) -> float:
    """Debit company balance with FOR UPDATE lock."""
    if amount < 0:
        raise ValueError("Debit amount must be >= 0")

    company = await _get_company_for_update(session, company_id)
    current_balance = float(company.balance)
    if current_balance < amount:
        raise ValueError(
            f"Insufficient balance: need {amount:.2f}, available {current_balance:.2f}"
        )
    company.balance = current_balance - amount
    await session.flush()
    return float(company.balance)


async def credit_balance(session: AsyncSession, company_id: int, amount: float) -> float:
    """Credit company balance with FOR UPDATE lock."""
    if amount < 0:
        raise ValueError("Credit amount must be >= 0")

    company = await _get_company_for_update(session, company_id)
    company.balance = float(company.balance) + amount
    await session.flush()
    return float(company.balance)


async def recalculate_net_worth(session: AsyncSession, company_id: int) -> float:
    """Recalculate and update a company's net worth."""
    company = await _get_company_for_update(session, company_id)

    inventory_value = float(
        (
            await session.execute(
                select(
                    func.coalesce(
                        func.sum(Inventory.quantity * Resource.base_price),
                        0,
                    )
                )
                .select_from(Inventory)
                .join(Resource, Resource.id == Inventory.resource_id)
                .where(Inventory.company_id == company_id)
            )
        ).scalar_one()
        or 0
    )
    building_value = float(
        (
            await session.execute(
                select(
                    func.coalesce(
                        func.sum(BuildingType.cost_credits),
                        0,
                    )
                )
                .select_from(Building)
                .join(BuildingType, BuildingType.id == Building.building_type_id)
                .where(Building.company_id == company_id)
            )
        ).scalar_one()
        or 0
    )

    company.net_worth = float(company.balance) + inventory_value + building_value
    await session.flush()
    return float(company.net_worth)


async def recalculate_all_net_worths(session: AsyncSession) -> int:
    """Recalculate net worth for all active companies. Returns count updated."""
    company_ids = (
        await session.execute(select(Company.id).where(Company.is_active.is_(True)))
    ).scalars().all()
    for company_id in company_ids:
        await recalculate_net_worth(session, company_id)
    return len(company_ids)


async def get_company_status(session: AsyncSession, company_id: int) -> dict:
    """Get full company status including balance, workers, buildings."""
    company = (
        await session.execute(select(Company).where(Company.id == company_id))
    ).scalar_one_or_none()
    if company is None:
        raise ValueError(f"Company {company_id} not found")

    worker = (
        await session.execute(select(Worker).where(Worker.company_id == company_id))
    ).scalar_one_or_none()
    building_count = int(
        (
            await session.execute(
                select(func.count(Building.id)).where(Building.company_id == company_id)
            )
        ).scalar_one()
        or 0
    )

    net_worth = await recalculate_net_worth(session, company_id)
    return {
        "company_id": company.id,
        "name": company.name,
        "founder_agent_id": company.founder_agent_id,
        "region_id": company.region_id,
        "balance": float(company.balance),
        "net_worth": net_worth,
        "is_active": bool(company.is_active),
        "worker_count": int(worker.count if worker else 0),
        "worker_satisfaction": float(worker.satisfaction if worker else 0),
        "building_count": building_count,
        "created_at": company.created_at.isoformat(),
    }


async def get_company_workers(session: AsyncSession, company_id: int) -> dict[str, Any]:
    """Get workforce details for a company."""
    company = (
        await session.execute(select(Company).where(Company.id == company_id))
    ).scalar_one_or_none()
    if company is None:
        raise ValueError(f"Company {company_id} not found")

    worker = (
        await session.execute(select(Worker).where(Worker.company_id == company_id))
    ).scalar_one_or_none()
    count = int(worker.count if worker else 0)
    satisfaction = float(worker.satisfaction if worker else 0.0)
    return {
        "company_id": company.id,
        "count": count,
        "satisfaction": satisfaction,
        "rat_consumption_per_tick": count * settings.WORKER_RAT_PER_TICK,
        "dw_consumption_per_tick": count * settings.WORKER_DW_PER_TICK,
        "productivity_modifier": _worker_productivity_modifier(satisfaction),
    }


async def get_agent_company(session: AsyncSession, agent_id: int) -> dict | None:
    """Get the active company owned by an agent, if any."""
    company = (
        await session.execute(
            select(Company)
            .where(Company.founder_agent_id == agent_id, Company.is_active.is_(True))
            .order_by(Company.id.desc())
        )
    ).scalar_one_or_none()
    if company is None:
        return None
    return await get_company_status(session, company.id)


async def check_bankruptcies(session: AsyncSession) -> list[int]:
    """Detect and mark bankrupt companies. Returns list of bankrupt company IDs."""
    company_ids = (await session.execute(select(Company.id))).scalars().all()
    bankrupt: list[int] = []
    for company_id in company_ids:
        company = await _get_company_for_update(session, company_id)
        net_worth = await recalculate_net_worth(session, company_id)
        if net_worth > 0:
            continue

        inventory_rows = (
            await session.execute(
                select(func.count(Inventory.id)).where(
                    Inventory.company_id == company_id,
                    Inventory.quantity > 0,
                )
            )
        ).scalar_one()
        building_rows = (
            await session.execute(
                select(func.count(Building.id)).where(Building.company_id == company_id)
            )
        ).scalar_one()
        if (inventory_rows or 0) == 0 and (building_rows or 0) == 0:
            company.is_active = False
            bankrupt.append(company_id)

    await session.flush()
    return bankrupt
