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

from sqlalchemy.ext.asyncio import AsyncSession


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

    Returns: [{"ticker", "name", "quantity", "reserved", "available"}]
    """
    raise NotImplementedError("Issue #5: Implement inventory service")


async def get_resource_quantity(
    session: AsyncSession, company_id: int, resource_ticker: str
) -> dict:
    """Get quantity info for a specific resource.

    Returns: {"quantity", "reserved", "available"}
    """
    raise NotImplementedError("Issue #5: Implement inventory service")
