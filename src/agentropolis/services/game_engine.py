"""Legacy scaffold game-engine stub.

This file still describes the earlier tick-orchestrator model.
Target architecture is converging on housekeeping/background orchestration,
lazy settlement, and explicit phase integration rather than a single tick loop.

Keep the runtime behavior unchanged for now; treat these stubs as migration-era
placeholders until the service is rewritten against the current plan.
"""

import asyncio
import logging

logger = logging.getLogger(__name__)


async def run_tick_loop() -> None:
    """Legacy scaffold tick-loop entrypoint stub."""
    raise NotImplementedError("Issue #6: Implement game engine tick loop")


async def execute_tick(tick_number: int) -> dict:
    """Legacy scaffold single-tick execution stub."""
    raise NotImplementedError("Issue #6: Implement game engine tick loop")


async def record_price_history(current_tick: int) -> None:
    """Legacy scaffold tick-based price-history recorder stub."""
    raise NotImplementedError("Issue #6: Implement game engine tick loop")
