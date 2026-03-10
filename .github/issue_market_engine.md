## Overview

Implement the market matching engine — continuous order-driven matching with regional isolation.

Orders match immediately on submission using price-time priority. Markets are isolated per region (A region's order book is separate from B region's). Execution price = maker price. Tax collected on each trade.

## Files

- **Modify**: `src/agentropolis/services/market_engine.py`
- **DO NOT TOUCH**: Model files, other services

## Function Signatures (Final)

```python
async def place_order(
    session: AsyncSession,
    agent_id: int,
    company_id: int,
    region_id: int,
    resource_id: int,
    order_type: str,       # "BUY" or "SELL"
    quantity: int,
    price: int,            # copper per unit
    time_in_force: str = "GTC",
) -> dict:
    """Place order and immediately attempt matching.

    Flow:
    1. Acquire advisory lock: pg_advisory_xact_lock(region_id * 1_000_000 + resource_id)
    2. Validate:
       - BUY: freeze balance (reserve_balance). total_cost = quantity * price
       - SELL: freeze inventory (reserve_resource)
    3. Insert Order row (with agent_id, region_id)
    4. Walk opposing book (same region_id, same resource_id):
       - BUY walks sells ASC by price, ASC by created_at
       - SELL walks buys DESC by price, ASC by created_at
       - Skip self-trade (same company_id)
       - Execute at maker (resting) price
       - For each fill:
         a. Transfer balance: buyer pays, seller receives
         b. Transfer inventory: seller loses, buyer gains
         c. Calculate tax: trade_amount * region.tax_rate (floor to int)
         d. Deduct tax from seller proceeds, add to region.treasury
         e. Create Trade row (with agent_ids, region_id, tax_collected)
         f. Update both orders (remaining, status)
    5. Handle remainder:
       - GTC: rest on book (OPEN or PARTIALLY_FILLED)
       - IOC: cancel remainder, unreserve

    Returns: {"order_id", "status", "remaining", "fills": [{"trade_id", "price", "quantity", "counterparty"}]}
    """

async def cancel_order(
    session: AsyncSession, company_id: int, order_id: int,
) -> bool:
    """Cancel open order. Unreserve balance (BUY) or inventory (SELL).
    Returns True if cancelled."""

async def get_order_book(
    session: AsyncSession, region_id: int, resource_id: int,
) -> dict:
    """Aggregated order book for a resource in a region.
    Returns: {"bids": [{"price", "quantity", "order_count"}], "asks": [...]}"""

async def get_my_orders(
    session: AsyncSession, company_id: int, status: str | None = "OPEN",
) -> list[dict]:
    """Get orders for a company, optionally filtered by status."""
```

## Implementation Rules

1. **Advisory lock per resource per region**: `pg_advisory_xact_lock(region_id * 1_000_000 + resource_id)` serializes matching
2. **Deadlock prevention**: when locking multiple company rows, lock in ascending company_id order
3. **Maker price execution**: incoming taker gets resting maker's price
4. **Self-trade prevention**: skip when `resting.company_id == incoming.company_id`
5. **Tax**: `tax = floor(execution_price * fill_quantity * region.tax_rate)`, deducted from seller proceeds
6. **Balance flow for BUY fill**:
   - Buyer: unreserve (price * qty), debit (execution_price * qty). If execution_price < order_price, refund difference
   - Seller: unreserve inventory, remove inventory, credit (execution_price * qty - tax)
7. **Inventory flow**: seller inventory decreases, buyer inventory increases (both in same region)
8. All operations through `inventory_svc` and `company_svc` (not direct DB writes)
9. Integer arithmetic throughout (copper)

## Matching Algorithm

```
# For a BUY order:
opposing = SELECT * FROM orders
    WHERE resource_id = X AND region_id = Y AND order_type = 'SELL'
    AND status IN ('OPEN', 'PARTIALLY_FILLED')
    ORDER BY price ASC, created_at ASC
    FOR UPDATE

for resting in opposing:
    if resting.company_id == incoming.company_id: continue  # self-trade
    if resting.price > incoming.price: break  # no match
    fill_qty = min(incoming.remaining, resting.remaining)
    exec_price = resting.price  # maker price
    # ... execute fill ...
```

## Acceptance Criteria

- [ ] Immediate matching on order placement
- [ ] Price-time priority
- [ ] Regional isolation (region_id scoping)
- [ ] Advisory lock per resource+region
- [ ] Maker price execution
- [ ] Self-trade prevention
- [ ] Tax collection to region treasury
- [ ] GTC vs IOC handling
- [ ] Balance/inventory freeze and release
- [ ] Cancel order with unreserve
- [ ] Integer arithmetic (copper)

## Dependencies

- **Depends on**: #16 (Foundation), #17 (inventory_svc), #18 (company_svc balance ops)
- **Blocks**: #22 (game_engine candle aggregation)
