## Overview

Implement the game engine — housekeeping sweep orchestrator running as background task.

The sweep runs every 60s as a safety net. It force-settles all companies, aggregates candles, recalculates net worths, checks bankruptcies, settles transport arrivals, and writes a HousekeepingLog.

## Files

- **Modify**: `src/agentropolis/services/game_engine.py`
- **Modify**: `src/agentropolis/main.py` (start/stop loop in lifespan)
- **DO NOT TOUCH**: Model files, other service files

## Function Signatures (Final)

```python
async def run_housekeeping_loop() -> None:
    """Main loop. Runs forever until cancelled.
    Started by FastAPI lifespan.
    Reads interval from GameState.housekeeping_interval_seconds.
    Uses pg_try_advisory_lock(1) to prevent concurrent sweeps."""

async def run_housekeeping_sweep(now: datetime | None = None) -> dict:
    """Execute single sweep.
    Order:
    1. Acquire pg_try_advisory_lock(1) — skip if another instance running
    2. settle_all_npc_consumption(now)
    3. For each active company: settle_company_buildings(now)
    4. settle_all_agent_vitals(now) — all agents
    5. settle_transport_arrivals(now) — deliver arrived shipments
    6. aggregate_candles(now)
    7. recalculate_all_net_worths()
    8. check_bankruptcies()
    9. Write HousekeepingLog record
    10. Update GameState.last_housekeeping_at = now

    Returns: {"period_start", "period_end", "consumption": {...},
              "production": {...}, "bankruptcies": [...], "transports_delivered": int}
    """

async def aggregate_candles(now: datetime | None = None) -> int:
    """Aggregate trades since last candle into OHLCV PriceHistory records.
    Groups by (resource_id, region_id, period_start).
    Period width = CANDLE_PERIOD_SECONDS (default 60s).
    Returns number of candles created/updated."""
```

## Implementation Rules

1. `pg_try_advisory_lock(1)` — non-blocking, skip sweep if lock not acquired
2. Use `async_session()` to create own sessions (not request-scoped)
3. Each step in its own transaction (commit between steps for partial progress)
4. Candle aggregation: group trades by floor(created_at / period_seconds) → compute OHLCV
5. Log errors per-company but don't abort sweep
6. `main.py` changes: uncomment loop start in lifespan, add cancel on shutdown

## main.py Integration

```python
# In lifespan:
import asyncio
from agentropolis.services.game_engine import run_housekeeping_loop

task = asyncio.create_task(run_housekeeping_loop())
yield
task.cancel()
try:
    await task
except asyncio.CancelledError:
    pass
```

## Acceptance Criteria

- [ ] Background loop with configurable interval
- [ ] Advisory lock prevents concurrent sweeps
- [ ] All settlement steps executed in order
- [ ] Candle aggregation groups by resource+region+period
- [ ] HousekeepingLog written after each sweep
- [ ] Error handling per company (no abort)
- [ ] main.py starts/stops loop
- [ ] Graceful shutdown

## Dependencies

- **Depends on**: #16-#21 (ALL other services must be implemented)
- **Blocks**: None (final service)
