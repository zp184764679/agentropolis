## Overview

Update Market + Inventory API endpoints for the evolution plan.

Changes: All endpoints now use Agent auth, regional scoping, integer amounts (copper).

## Files

- **Modify**: `src/agentropolis/api/market.py`
- **Modify**: `src/agentropolis/api/inventory.py`
- **DO NOT TOUCH**: Other API files, services, models

## api/market.py Changes

All endpoints change from `get_current_company` to `get_current_agent`. Company is resolved from Agent context (agent's company in current region).

```python
# Helper to get agent's company in current region
async def get_agent_company(session, agent) -> Company:
    """Resolve agent's company in their current region.
    Raises 400 if agent has no company in current region."""

GET  /api/market/prices?region_id=X     → list[MarketPrice]
    region_id defaults to agent's current region if authed

GET  /api/market/orderbook/{resource_id}?region_id=X → OrderBookResponse
    region_id required

GET  /api/market/history/{resource_id}?region_id=X   → list[PriceCandle]

POST /api/market/buy                    → OrderResponse
    Auth: get_current_agent → resolve company
    Body: {"resource_id": int, "quantity": int, "price": int, "time_in_force": "GTC"}
    Calls: market_engine.place_order(agent_id, company_id, region_id, ...)

POST /api/market/sell                   → OrderResponse
    Same pattern as buy

POST /api/market/cancel                 → OrderResponse
    Body: {"order_id": int}

GET  /api/market/orders?status=OPEN     → list[OrderResponse]

GET  /api/market/trades?resource_id=X&minutes=10 → list[TradeRecord]

GET  /api/market/analysis/{resource_id}?region_id=X → MarketAnalysis
```

## api/inventory.py Changes

```python
GET  /api/inventory?region_id=X         → InventoryResponse
    Auth: get_current_agent
    region_id optional (None = all regions)
    Can query company inventory OR personal inventory via ?owner=company|agent

GET  /api/inventory/{resource_id}?region_id=X → InventoryItem

GET  /api/inventory/info/{resource_id}  → ResourceInfo (no auth)
```

## Key Patterns

1. Auth: `agent: Agent = Depends(get_current_agent)` on all protected endpoints
2. Region: defaults to `agent.current_region_id` if not specified
3. Company resolution: look up Company where `founder_agent_id = agent.id` and `region_id` matches
4. All prices/quantities in int (copper)
5. Commit session after mutations
6. ValueError from services → HTTPException(400)

## Acceptance Criteria

- [ ] All market endpoints use Agent auth
- [ ] Regional scoping on all endpoints
- [ ] Company resolved from Agent context
- [ ] Integer amounts throughout
- [ ] Order book aggregated by region
- [ ] Trade history filterable by region
- [ ] Inventory supports company vs personal owner

## Dependencies

- **Depends on**: #16 (Foundation), #17 (inventory_svc), #21 (market_engine), #22 (leaderboard)
- **Blocks**: None
