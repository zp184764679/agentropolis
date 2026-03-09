"""NPC shop service - NPC vendor buy/sell with dynamic pricing.

Dynamic pricing: effective_price = base_price * (1 + elasticity * (1 - stock / max_stock))
Low stock → higher prices. High stock → lower prices.
Reputation modifier stacks on top.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentropolis.config import settings
from agentropolis.models.npc_shop import NpcShop


def calculate_dynamic_price(
    base_price: int,
    current_stock: int,
    max_stock: int,
    elasticity: float,
) -> int:
    """Calculate dynamic price based on stock level.

    effective_price = base_price * (1 + elasticity * (1 - stock / max_stock))
    """
    if max_stock <= 0:
        return base_price

    stock_ratio = current_stock / max_stock
    multiplier = 1.0 + elasticity * (1.0 - stock_ratio)

    # Clamp multiplier
    multiplier = max(
        settings.NPC_SHOP_MIN_PRICE_MULTIPLIER,
        min(settings.NPC_SHOP_MAX_PRICE_MULTIPLIER, multiplier),
    )

    return max(1, int(base_price * multiplier))


async def get_effective_prices(
    session: AsyncSession,
    shop_id: int,
    reputation: float = 0.0,
    agent_id: int | None = None,
) -> dict:
    """Get effective buy/sell prices for a shop considering stock, reputation, and strategy.

    When agent_id is provided, applies strategy profile and trait modifiers:
    - Low risk tolerance → NPC discount
    - ISOLATIONIST stance → NPC discount
    - MERCHANT_PRINCE trait → NPC discount
    - IRON_TRADER trait → trade tax reduction

    Returns: {"buy_prices": {ticker: price}, "sell_prices": {ticker: price}}
    """
    from agentropolis.services.reputation_svc import get_reputation_modifier

    result = await session.execute(
        select(NpcShop).where(NpcShop.id == shop_id)
    )
    shop = result.scalar_one_or_none()
    if shop is None:
        raise ValueError(f"Shop {shop_id} not found")

    rep_modifier = get_reputation_modifier(reputation)

    # Strategy + trait modifier (discount for buy prices)
    strategy_modifier = 1.0
    if agent_id is not None:
        try:
            from agentropolis.services.training_hooks import get_npc_price_modifier
            strategy_modifier = await get_npc_price_modifier(session, agent_id)
        except Exception:
            strategy_modifier = 1.0

    max_stock = shop.max_stock or {}
    current_stock = shop.stock or {}
    elasticity = shop.elasticity if shop.elasticity is not None else settings.NPC_SHOP_DEFAULT_ELASTICITY

    effective_buy: dict[str, int] = {}
    for ticker, base_price in (shop.buy_prices or {}).items():
        ms = max_stock.get(ticker, 100)
        cs = current_stock.get(ticker, 0)
        dynamic = calculate_dynamic_price(base_price, cs, ms, elasticity)
        # Buy from shop: lower price = better for agent
        effective_buy[ticker] = max(1, int(dynamic * rep_modifier * strategy_modifier))

    effective_sell: dict[str, int] = {}
    for ticker, base_price in (shop.sell_prices or {}).items():
        ms = max_stock.get(ticker, 100)
        cs = current_stock.get(ticker, 0)
        dynamic = calculate_dynamic_price(base_price, cs, ms, elasticity)
        effective_sell[ticker] = max(1, int(dynamic * rep_modifier))

    return {"buy_prices": effective_buy, "sell_prices": effective_sell}


async def buy_from_shop(
    session: AsyncSession,
    agent_id: int,
    shop_id: int,
    resource_ticker: str,
    quantity: int,
) -> dict:
    """Buy resources from an NPC shop.

    Returns: {"cost", "quantity", "new_balance"}
    """
    raise NotImplementedError("Issue #27: Implement NPC shop service (base buy logic)")


async def sell_to_shop(
    session: AsyncSession,
    agent_id: int,
    shop_id: int,
    resource_ticker: str,
    quantity: int,
) -> dict:
    """Sell resources to an NPC shop.

    Returns: {"revenue", "quantity", "new_balance"}
    """
    raise NotImplementedError("Issue #27: Implement NPC shop service (base sell logic)")


async def get_shops_in_region(session: AsyncSession, region_id: int) -> list[dict]:
    """Get all NPC shops in a region with effective prices."""
    result = await session.execute(
        select(NpcShop).where(NpcShop.region_id == region_id)
    )
    shops = result.scalars().all()

    return [
        {
            "shop_id": s.id,
            "region_id": s.region_id,
            "shop_type": s.shop_type,
            "buy_prices": s.buy_prices or {},
            "sell_prices": s.sell_prices or {},
            "stock": s.stock or {},
            "max_stock": s.max_stock or {},
            "elasticity": s.elasticity,
        }
        for s in shops
    ]


async def restock_shops(session: AsyncSession) -> int:
    """Restock all NPC shops based on elapsed time. Returns count restocked."""
    raise NotImplementedError("Issue #27: Implement NPC shop service (restock logic)")
