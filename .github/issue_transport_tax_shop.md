## Overview

Implement Transport service + Tax service + NPC Shop service — regional logistics, trade taxation, and NPC vendors.

These three services form the regional economy infrastructure. Transport moves goods between regions, tax collects on trades, NPC shops provide baseline buy/sell prices.

## Files

- **Create**: `src/agentropolis/services/transport_svc.py`
- **Create**: `src/agentropolis/services/tax_svc.py`
- **Create**: `src/agentropolis/services/npc_shop_svc.py`
- **DO NOT TOUCH**: Model files, other services

## transport_svc.py

```python
async def create_shipment(
    session: AsyncSession, *,
    agent_id: int | None = None, company_id: int | None = None,
    from_region_id: int, to_region_id: int,
    items: dict[int, int],  # {resource_id: quantity}
    transport_type: str = "backpack",
    now: datetime | None = None,
) -> dict:
    """Create a transport order.
    1. Validate items exist in inventory at from_region
    2. Calculate total weight (sum of quantity * resource.weight_kg)
    3. Validate weight <= transport capacity
    4. Calculate route (shortest path) and travel time (adjusted by transport speed)
    5. Calculate cost: 1000 * (distance/100) * (weight/100) * (1 + danger/10) copper
    6. Debit cost from balance
    7. Remove items from inventory at from_region
    8. Create TransportOrder (status=IN_TRANSIT)

    Returns: {"transport_id", "from_region", "to_region", "items", "cost",
              "departed_at", "arrives_at", "transport_type"}
    Raises: ValueError if insufficient inventory/balance/capacity"""

async def settle_transport_arrivals(
    session: AsyncSession, now: datetime | None = None,
) -> dict:
    """Deliver all arrived shipments. Called by housekeeping.
    For each TransportOrder where arrives_at <= now AND status=IN_TRANSIT:
    1. Add items to owner's inventory at to_region
    2. Set status = DELIVERED
    Returns: {"delivered": int, "items_moved": dict}"""

async def get_shipments(
    session: AsyncSession, *, agent_id: int | None = None, company_id: int | None = None,
    status: str | None = None,
) -> list[dict]:
    """Get shipments for owner, optionally filtered by status."""

async def get_route_info(
    session: AsyncSession, from_region_id: int, to_region_id: int,
    weight: int = 0,
) -> dict:
    """Calculate route info without creating shipment.
    Returns: {"path", "distance_seconds", "cost", "danger_total"}"""
```

### Transport Types (constants)
```python
TRANSPORT_TYPES = {
    "backpack":  {"capacity_kg": 30,   "speed_mult": 1.0},
    "pack_horse": {"capacity_kg": 150,  "speed_mult": 0.8},
    "light_cart": {"capacity_kg": 500,  "speed_mult": 0.6},
    "heavy_cart": {"capacity_kg": 1500, "speed_mult": 0.4},
    "caravan":   {"capacity_kg": 5000, "speed_mult": 0.3},
}
```

## tax_svc.py

```python
async def collect_trade_tax(
    session: AsyncSession, region_id: int, trade_amount: int,
    payer_agent_id: int | None = None, payer_company_id: int | None = None,
) -> int:
    """Calculate and record trade tax.
    tax = floor(trade_amount * region.tax_rate)
    Adds to region.treasury. Creates TaxRecord.
    Returns: tax amount (copper)"""

async def collect_transport_tax(
    session: AsyncSession, region_id: int, transport_cost: int,
    payer_agent_id: int | None = None, payer_company_id: int | None = None,
) -> int:
    """Tax on transport originating from region. 10% of transport cost.
    Returns: tax amount"""

async def get_tax_records(
    session: AsyncSession, region_id: int | None = None, limit: int = 50,
) -> list[dict]:
    """Get recent tax records."""

async def get_region_treasury(session: AsyncSession, region_id: int) -> int:
    """Get region treasury balance (copper)."""
```

## npc_shop_svc.py

```python
async def buy_from_npc(
    session: AsyncSession, agent_id: int, region_id: int,
    resource_id: int, quantity: int,
) -> dict:
    """Agent buys from NPC shop.
    1. Find NpcShop in region that sells this resource
    2. Check stock >= quantity
    3. price = shop.sell_prices[resource] * quantity (sell_prices = prices shop sells AT)
    4. Debit agent.personal_balance
    5. Add to agent inventory at region
    6. Decrease shop stock
    Returns: {"resource_id", "quantity", "total_cost", "remaining_stock"}
    Raises: ValueError if no shop, insufficient stock/balance"""

async def sell_to_npc(
    session: AsyncSession, agent_id: int, region_id: int,
    resource_id: int, quantity: int,
) -> dict:
    """Agent sells to NPC shop.
    price = shop.buy_prices[resource] * quantity (buy_prices = prices shop buys AT)
    Returns: {"resource_id", "quantity", "total_earned", "remaining_stock"}"""

async def get_npc_shops(session: AsyncSession, region_id: int) -> list[dict]:
    """Get all NPC shops in a region with their prices and stock."""

async def restock_shops(session: AsyncSession, now: datetime | None = None) -> int:
    """Restock NPC shops based on restock_rate and elapsed time.
    Called by housekeeping. Returns shops_restocked count."""
```

## Acceptance Criteria

- [ ] Transport: create, settle arrivals, get status
- [ ] Weight/capacity validation
- [ ] Route cost calculation using pathfinding
- [ ] Tax collection on trades and transport
- [ ] TaxRecord created for each tax event
- [ ] Region treasury updated
- [ ] NPC shop buy/sell with stock management
- [ ] NPC shop restock over time
- [ ] All amounts in copper (int)

## Dependencies

- **Depends on**: #16 (Foundation), #17 (inventory_svc), #24 (world_svc for pathfinding)
- **Blocks**: #22 (game_engine transport settlement), API routes
