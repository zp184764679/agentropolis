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

from agentropolis.models import Inventory, Resource


async def add_resource(
    session: AsyncSession, company_id: int, resource_ticker: str, amount: float
) -> float:
    """Add resources to inventory. Creates row if not exists.

    Returns: new quantity
    """
    raise NotImplementedError("Issue #5: Implement inventory service")


async def remove_resource(
    session: AsyncSession, company_id: int, resource_ticker: str, amount: float
) -> float:
    """Remove resources from inventory.

    Returns: new quantity
    Raises: ValueError if insufficient available quantity
    """
    raise NotImplementedError("Issue #5: Implement inventory service")


async def reserve_resource(
    session: AsyncSession, company_id: int, resource_ticker: str, amount: float
) -> float:
    """Reserve resources (for sell orders). Does not reduce quantity.

    Returns: new reserved amount
    Raises: ValueError if insufficient available (quantity - reserved)
    """
    raise NotImplementedError("Issue #5: Implement inventory service")


async def unreserve_resource(
    session: AsyncSession, company_id: int, resource_ticker: str, amount: float
) -> float:
    """Release reserved resources (on order cancel).

    Returns: new reserved amount
    """
    raise NotImplementedError("Issue #5: Implement inventory service")


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
                "base_price": float(base_price or 0),
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
        "base_price": float(base_price or 0),
    }
