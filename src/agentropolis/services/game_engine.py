"""Game engine - tick orchestrator.

Runs as an asyncio background task started in FastAPI lifespan.
Uses pg_try_advisory_lock to ensure only one instance runs the tick.

Tick execution order (MUST be sequential):
1. Consumption phase → consumption.tick_consumption()
2. Production phase  → production.tick_production(satisfaction_map)
3. Matching phase    → market_engine.match_all_resources()
4. Recording phase   → record OHLC prices, update net worths, write TickLog

The tick loop:
- Sleeps for tick_interval_seconds between ticks
- Acquires advisory lock 1 before executing (pg_try_advisory_lock(1))
- If lock not acquired, skip (another instance is running)
- Updates GameState.current_tick and GameState.last_tick_at

Dependencies: ALL other services must be implemented first.
This is the orchestrator that ties everything together.
"""

import asyncio
import logging

logger = logging.getLogger(__name__)


async def run_tick_loop() -> None:
    """Main tick loop. Runs forever until cancelled.

    Started by FastAPI lifespan. Reads tick_interval from GameState.
    """
    raise NotImplementedError("Issue #6: Implement game engine tick loop")


async def execute_tick(tick_number: int) -> dict:
    """Execute a single game tick.

    Returns: {"tick": int, "consumption": {...}, "production": {...}, "trades": {...}}
    """
    raise NotImplementedError("Issue #6: Implement game engine tick loop")


async def record_price_history(current_tick: int) -> None:
    """Record OHLCV data for all resources at end of tick."""
    raise NotImplementedError("Issue #6: Implement game engine tick loop")
