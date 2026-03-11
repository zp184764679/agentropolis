"""Inventory service - resource stockpile management.

All quantity mutations must use SELECT ... FOR UPDATE to prevent races.

Operations:
- add: Increase quantity (from production output, trade buy)
- remove: Decrease quantity (from production input, trade sell)
- reserve: Mark quantity as reserved (for open sell orders)
- unreserve: Release reserved quantity (on order cancel)

Invariants:
- quantity >= 0 always
- reserved >= 0 always
- reserved <= quantity always
- available = quantity - reserved >= 0 always
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agentropolis.models import Agent, Company, Inventory, Region, Resource


async def _resolve_company_region_id(
    session: AsyncSession,
    *,
    company_id: int,
    region_id: int | None = None,
) -> int:
    if region_id is not None:
        region = await session.get(Region, region_id)
        if region is None:
            raise ValueError(f"Region {region_id} not found")
        return region.id

    company = (
        await session.execute(select(Company).where(Company.id == company_id))
    ).scalar_one_or_none()
    if company is None:
        raise ValueError(f"Company {company_id} not found")
    if company.region_id is not None:
        return company.region_id
    if company.founder_agent_id is not None:
        founder = await session.get(Agent, company.founder_agent_id)
        if founder is not None:
            return founder.current_region_id

    region = (
        await session.execute(select(Region).order_by(Region.id.asc()))
    ).scalar_one_or_none()
    if region is None:
        raise ValueError("No regions available")
    return region.id


async def _get_resource(session: AsyncSession, resource_ticker: str) -> Resource:
    resource = (
        await session.execute(select(Resource).where(Resource.ticker == resource_ticker))
    ).scalar_one_or_none()
    if resource is None:
        raise ValueError(f"Unknown resource ticker: {resource_ticker}")
    return resource


async def _get_or_create_inventory_row(
    session: AsyncSession,
    *,
    company_id: int,
    region_id: int,
    resource_id: int,
) -> Inventory:
    result = await session.execute(
        select(Inventory)
        .where(
            Inventory.company_id == company_id,
            Inventory.agent_id.is_(None),
            Inventory.region_id == region_id,
            Inventory.resource_id == resource_id,
        )
        .with_for_update()
    )
    inventory = result.scalar_one_or_none()
    if inventory is None:
        inventory = Inventory(
            company_id=company_id,
            agent_id=None,
            region_id=region_id,
            resource_id=resource_id,
            quantity=0,
            reserved=0,
        )
        session.add(inventory)
        await session.flush()
    return inventory


async def add_resource(
    session: AsyncSession,
    company_id: int,
    resource_ticker: str,
    amount: float,
    *,
    region_id: int | None = None,
) -> float:
    """Add resources to inventory. Creates row if not exists.

    Returns: new quantity
    """
    if amount <= 0:
        raise ValueError("amount must be greater than 0")
    resolved_region_id = await _resolve_company_region_id(
        session,
        company_id=company_id,
        region_id=region_id,
    )
    from agentropolis.services.storage_svc import check_storage_available

    has_capacity = await check_storage_available(
        session,
        amount,
        resolved_region_id,
        company_id=company_id,
    )
    if not has_capacity:
        raise ValueError(
            f"Storage capacity exceeded in region {resolved_region_id}: need {amount:.4f} additional units"
        )
    resource = await _get_resource(session, resource_ticker)
    inventory = await _get_or_create_inventory_row(
        session,
        company_id=company_id,
        region_id=resolved_region_id,
        resource_id=resource.id,
    )
    inventory.quantity = float(inventory.quantity) + amount
    await session.flush()
    return float(inventory.quantity)


async def remove_resource(
    session: AsyncSession,
    company_id: int,
    resource_ticker: str,
    amount: float,
    *,
    region_id: int | None = None,
) -> float:
    """Remove resources from inventory.

    Returns: new quantity
    Raises: ValueError if insufficient available quantity
    """
    if amount <= 0:
        raise ValueError("amount must be greater than 0")
    resolved_region_id = await _resolve_company_region_id(
        session,
        company_id=company_id,
        region_id=region_id,
    )
    resource = await _get_resource(session, resource_ticker)
    inventory = await _get_or_create_inventory_row(
        session,
        company_id=company_id,
        region_id=resolved_region_id,
        resource_id=resource.id,
    )
    available = float(inventory.quantity) - float(inventory.reserved)
    if available < amount:
        raise ValueError(
            f"Insufficient {resource_ticker}: need {amount:.4f}, available {available:.4f}"
        )
    inventory.quantity = float(inventory.quantity) - amount
    await session.flush()
    return float(inventory.quantity)


async def reserve_resource(
    session: AsyncSession,
    company_id: int,
    resource_ticker: str,
    amount: float,
    *,
    region_id: int | None = None,
) -> float:
    """Reserve resources (for sell orders). Does not reduce quantity.

    Returns: new reserved amount
    Raises: ValueError if insufficient available (quantity - reserved)
    """
    if amount <= 0:
        raise ValueError("amount must be greater than 0")
    resolved_region_id = await _resolve_company_region_id(
        session,
        company_id=company_id,
        region_id=region_id,
    )
    resource = await _get_resource(session, resource_ticker)
    inventory = await _get_or_create_inventory_row(
        session,
        company_id=company_id,
        region_id=resolved_region_id,
        resource_id=resource.id,
    )
    available = float(inventory.quantity) - float(inventory.reserved)
    if available < amount:
        raise ValueError(
            f"Insufficient {resource_ticker}: need {amount:.4f}, available {available:.4f}"
        )
    inventory.reserved = float(inventory.reserved) + amount
    await session.flush()
    return float(inventory.reserved)


async def unreserve_resource(
    session: AsyncSession,
    company_id: int,
    resource_ticker: str,
    amount: float,
    *,
    region_id: int | None = None,
) -> float:
    """Release reserved resources (on order cancel).

    Returns: new reserved amount
    """
    if amount <= 0:
        raise ValueError("amount must be greater than 0")
    resolved_region_id = await _resolve_company_region_id(
        session,
        company_id=company_id,
        region_id=region_id,
    )
    resource = await _get_resource(session, resource_ticker)
    inventory = await _get_or_create_inventory_row(
        session,
        company_id=company_id,
        region_id=resolved_region_id,
        resource_id=resource.id,
    )
    if float(inventory.reserved) < amount:
        raise ValueError(
            f"Cannot unreserve {amount:.4f} {resource_ticker}; reserved is {float(inventory.reserved):.4f}"
        )
    inventory.reserved = float(inventory.reserved) - amount
    await session.flush()
    return float(inventory.reserved)


async def get_inventory(session: AsyncSession, company_id: int) -> list[dict]:
    """Get full inventory for a company.

    Returns: [{"ticker", "name", "quantity", "reserved", "available", "base_price"}]
    """
    result = await session.execute(
        select(
            Resource.ticker,
            Resource.name,
            Resource.base_price,
            func.coalesce(func.sum(Inventory.quantity), 0).label("quantity"),
            func.coalesce(func.sum(Inventory.reserved), 0).label("reserved"),
        )
        .join(Inventory, Inventory.resource_id == Resource.id)
        .where(Inventory.company_id == company_id)
        .group_by(Resource.id, Resource.ticker, Resource.name, Resource.base_price)
        .order_by(Resource.ticker.asc())
    )

    items: list[dict] = []
    for ticker, name, base_price, quantity, reserved in result.all():
        quantity_value = float(quantity or 0)
        reserved_value = float(reserved or 0)
        items.append(
            {
                "ticker": ticker,
                "name": name,
                "quantity": quantity_value,
                "reserved": reserved_value,
                "available": quantity_value - reserved_value,
                "base_price": int(base_price or 0),
            }
        )
    return items


async def get_resource_quantity(
    session: AsyncSession, company_id: int, resource_ticker: str
) -> dict:
    """Get quantity info for a specific resource.

    Returns: {"ticker", "name", "quantity", "reserved", "available", "base_price"}
    Raises: ValueError if the resource ticker does not exist
    """
    result = await session.execute(
        select(
            Resource.ticker,
            Resource.name,
            Resource.base_price,
            func.coalesce(func.sum(Inventory.quantity), 0).label("quantity"),
            func.coalesce(func.sum(Inventory.reserved), 0).label("reserved"),
        )
        .select_from(Resource)
        .outerjoin(
            Inventory,
            (Inventory.resource_id == Resource.id) & (Inventory.company_id == company_id),
        )
        .where(Resource.ticker == resource_ticker)
        .group_by(Resource.id, Resource.ticker, Resource.name, Resource.base_price)
    )
    row = result.one_or_none()
    if row is None:
        raise ValueError(f"Unknown resource ticker: {resource_ticker}")

    ticker, name, base_price, quantity, reserved = row
    quantity_value = float(quantity or 0)
    reserved_value = float(reserved or 0)
    return {
        "ticker": ticker,
        "name": name,
        "quantity": quantity_value,
        "reserved": reserved_value,
        "available": quantity_value - reserved_value,
        "base_price": int(base_price or 0),
    }


async def get_resource_quantity_in_region(
    session: AsyncSession,
    company_id: int,
    resource_ticker: str,
    *,
    region_id: int | None = None,
) -> dict:
    """Get quantity info for a specific resource in one company region."""
    resolved_region_id = await _resolve_company_region_id(
        session,
        company_id=company_id,
        region_id=region_id,
    )
    resource = await _get_resource(session, resource_ticker)
    inventory = await _get_or_create_inventory_row(
        session,
        company_id=company_id,
        region_id=resolved_region_id,
        resource_id=resource.id,
    )
    quantity_value = float(inventory.quantity or 0)
    reserved_value = float(inventory.reserved or 0)
    return {
        "ticker": resource.ticker,
        "name": resource.name,
        "quantity": quantity_value,
        "reserved": reserved_value,
        "available": quantity_value - reserved_value,
        "base_price": int(resource.base_price or 0),
        "region_id": resolved_region_id,
    }


async def consume_reserved_resource(
    session: AsyncSession,
    company_id: int,
    resource_ticker: str,
    amount: float,
    *,
    region_id: int | None = None,
) -> dict:
    """Consume quantity that is already reserved for a sell-side execution."""
    if amount <= 0:
        raise ValueError("amount must be greater than 0")
    resolved_region_id = await _resolve_company_region_id(
        session,
        company_id=company_id,
        region_id=region_id,
    )
    resource = await _get_resource(session, resource_ticker)
    inventory = await _get_or_create_inventory_row(
        session,
        company_id=company_id,
        region_id=resolved_region_id,
        resource_id=resource.id,
    )
    if float(inventory.reserved) < amount:
        raise ValueError(
            f"Insufficient reserved {resource_ticker}: need {amount:.4f}, reserved {float(inventory.reserved):.4f}"
        )
    if float(inventory.quantity) < amount:
        raise ValueError(
            f"Insufficient quantity {resource_ticker}: need {amount:.4f}, quantity {float(inventory.quantity):.4f}"
        )
    inventory.reserved = float(inventory.reserved) - amount
    inventory.quantity = float(inventory.quantity) - amount
    await session.flush()
    return {
        "ticker": resource.ticker,
        "quantity": float(inventory.quantity),
        "reserved": float(inventory.reserved),
        "available": float(inventory.quantity) - float(inventory.reserved),
        "region_id": resolved_region_id,
    }
