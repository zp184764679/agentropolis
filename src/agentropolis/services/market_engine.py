"""Legacy scaffold market-engine stub.

This module still describes batch matching keyed to game ticks and company-owned
orders. The target plan moves toward regional, agent-aware market interactions
with a contract surface shared across REST and MCP.

Use these stubs as migration placeholders, not as the final market semantics.
"""

from sqlalchemy.ext.asyncio import AsyncSession


async def match_all_resources(session: AsyncSession, current_tick: int) -> dict:
    """Legacy scaffold batch-match stub. Returns trade summary.

    Args:
        session: DB session (caller manages transaction)
        current_tick: Current game tick number

    Returns:
        {"total_trades": int, "total_volume": float, "by_resource": {ticker: {trades, volume}}}
    """
    raise NotImplementedError("Issue #1: Implement market matching engine")


async def place_buy_order(
    session: AsyncSession,
    company_id: int,
    resource_ticker: str,
    quantity: float,
    price: float,
    current_tick: int,
) -> int:
    """Legacy scaffold buy-order stub. Reserves balance (price * quantity).

    Returns: order_id
    Raises: ValueError if insufficient balance or invalid resource
    """
    raise NotImplementedError("Issue #1: Implement market matching engine")


async def place_sell_order(
    session: AsyncSession,
    company_id: int,
    resource_ticker: str,
    quantity: float,
    price: float,
    current_tick: int,
) -> int:
    """Legacy scaffold sell-order stub. Reserves inventory quantity.

    Returns: order_id
    Raises: ValueError if insufficient inventory or invalid resource
    """
    raise NotImplementedError("Issue #1: Implement market matching engine")


async def cancel_order(session: AsyncSession, company_id: int, order_id: int) -> bool:
    """Legacy scaffold order-cancel stub. Unreserves balance or inventory.

    Returns: True if cancelled, False if order not found or not owned
    """
    raise NotImplementedError("Issue #1: Implement market matching engine")


async def get_order_book(session: AsyncSession, resource_ticker: str) -> dict:
    """Legacy scaffold order-book stub.

    Returns: {"bids": [{"price", "quantity", "order_count"}], "asks": [...]}
    """
    raise NotImplementedError("Issue #1: Implement market matching engine")


async def get_my_orders(
    session: AsyncSession, company_id: int, status: str | None = "OPEN"
) -> list[dict]:
    """Legacy scaffold company-order query stub."""
    raise NotImplementedError("Issue #1: Implement market matching engine")
