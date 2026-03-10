## Overview

Implement leaderboard service — rankings, market analysis, trade/price history.

Read-only service. Queries existing data, no mutations.

## Files

- **Modify**: `src/agentropolis/services/leaderboard.py`
- **DO NOT TOUCH**: Model files, other services

## Function Signatures (Final)

```python
async def get_leaderboard(
    session: AsyncSession, metric: str = "net_worth", limit: int = 20,
    region_id: int | None = None,
) -> list[dict]:
    """Ranked leaderboard, optionally filtered by region.
    Metrics: "net_worth", "balance", "npc_workers", "buildings"
    Returns: [{"rank", "company_name", "net_worth", "balance",
               "npc_worker_count", "building_count", "region_name"}]"""

async def get_market_analysis(
    session: AsyncSession, resource_id: int, region_id: int,
) -> dict:
    """Analyze market for a resource in a region.
    Returns: {"resource_id", "avg_price_10m", "price_trend", "supply_demand_ratio",
              "total_buy_volume", "total_sell_volume", "trade_count_10m"}
    price_trend: compare avg of last 5min vs prior 5min → "rising"/"falling"/"stable" """

async def get_trade_history(
    session: AsyncSession, resource_id: int | None = None,
    region_id: int | None = None, minutes: int = 10,
) -> list[dict]:
    """Recent trades. Returns: [{"trade_id", "buyer", "seller", "resource_ticker",
    "price", "quantity", "region_name", "executed_at"}]"""

async def get_price_history(
    session: AsyncSession, resource_id: int, region_id: int, periods: int = 50,
) -> list[dict]:
    """OHLCV candles. Returns: [{"period_start", "open", "high", "low", "close",
    "volume", "period_seconds", "trade_count"}]"""
```

## Implementation Rules

1. All queries are read-only (no FOR UPDATE needed)
2. Leaderboard sorts by chosen metric DESC, assigns rank 1-N
3. Market analysis: 10-minute rolling window using `Trade.created_at`
4. Price trend: compare avg price in [now-10m, now-5m] vs [now-5m, now] → "rising" if >5% increase, "falling" if >5% decrease, else "stable"
5. Supply/demand ratio = total_sell_volume / total_buy_volume (from open orders)
6. Trade history filters by `Trade.created_at >= now - minutes`
7. Price history reads from `PriceHistory` table (populated by game_engine candle aggregation)
8. All prices in copper (int)
9. `region_id` filtering: if provided, scope to that region; if None, aggregate globally

## Acceptance Criteria

- [ ] Leaderboard with 4 metric options
- [ ] Optional region filtering
- [ ] Market analysis with trend detection
- [ ] Trade history with time window
- [ ] Price history from candle data
- [ ] All values in copper (int)

## Dependencies

- **Depends on**: #16 (Foundation)
- **Blocks**: #22 (game_engine), API routes
