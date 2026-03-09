"""Currency service - inflation monitoring and money supply tracking."""

from sqlalchemy.ext.asyncio import AsyncSession


async def calculate_inflation_index(session: AsyncSession) -> float:
    """Calculate current inflation index based on money supply vs GDP.

    Returns: inflation index (1.0 = stable)
    """
    raise NotImplementedError("Issue #29: Implement currency service")


async def get_total_currency_supply(session: AsyncSession) -> int:
    """Calculate total copper in circulation (agent + company balances).

    Returns: total copper
    """
    raise NotImplementedError("Issue #29: Implement currency service")


async def update_game_state_economics(session: AsyncSession) -> dict:
    """Update GameState with latest inflation_index and total_currency_supply."""
    raise NotImplementedError("Issue #29: Implement currency service")
