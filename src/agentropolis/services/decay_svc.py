"""Perishable goods decay service.

RAT and DW decay over time when stored in inventory.
qty_lost = floor(qty * decay_rate_per_hour * elapsed_hours)
"""

import logging
import math
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentropolis.models.inventory import Inventory
from agentropolis.models.resource import Resource

logger = logging.getLogger(__name__)


async def settle_inventory_decay(
    session: AsyncSession,
    inventory_id: int,
    now: datetime | None = None,
) -> dict:
    """Settle decay for a single inventory row.

    Returns: {"inventory_id", "resource_ticker", "qty_before", "qty_lost", "qty_after"}
    """
    if now is None:
        now = datetime.now(UTC)

    result = await session.execute(
        select(Inventory).where(Inventory.id == inventory_id).with_for_update()
    )
    inv = result.scalar_one_or_none()
    if inv is None:
        raise ValueError(f"Inventory {inventory_id} not found")

    if inv.quantity <= 0:
        return {
            "inventory_id": inventory_id,
            "qty_before": 0,
            "qty_lost": 0,
            "qty_after": 0,
        }

    # Get resource info
    result = await session.execute(
        select(Resource).where(Resource.id == inv.resource_id)
    )
    resource = result.scalar_one()

    if not resource.is_perishable or resource.decay_rate_per_hour <= 0:
        return {
            "inventory_id": inventory_id,
            "resource_ticker": resource.ticker,
            "qty_before": inv.quantity,
            "qty_lost": 0,
            "qty_after": inv.quantity,
        }

    # Compute elapsed
    if inv.last_decay_at is None:
        inv.last_decay_at = now
        await session.flush()
        return {
            "inventory_id": inventory_id,
            "resource_ticker": resource.ticker,
            "qty_before": inv.quantity,
            "qty_lost": 0,
            "qty_after": inv.quantity,
        }

    elapsed_hours = (now - inv.last_decay_at).total_seconds() / 3600.0
    if elapsed_hours <= 0:
        return {
            "inventory_id": inventory_id,
            "resource_ticker": resource.ticker,
            "qty_before": inv.quantity,
            "qty_lost": 0,
            "qty_after": inv.quantity,
        }

    qty_before = inv.quantity
    qty_lost = math.floor(inv.quantity * resource.decay_rate_per_hour * elapsed_hours)
    qty_lost = min(qty_lost, inv.quantity - inv.reserved)  # Don't decay reserved items

    if qty_lost > 0:
        inv.quantity -= qty_lost

    inv.last_decay_at = now
    await session.flush()

    return {
        "inventory_id": inventory_id,
        "resource_ticker": resource.ticker,
        "qty_before": qty_before,
        "qty_lost": qty_lost,
        "qty_after": inv.quantity,
    }


async def settle_all_perishable_decay(
    session: AsyncSession,
    now: datetime | None = None,
) -> dict:
    """Settle decay for all perishable inventory items. Housekeeping task.

    Returns: {"items_processed", "total_qty_lost"}
    """
    if now is None:
        now = datetime.now(UTC)

    # Get IDs of perishable resources
    result = await session.execute(
        select(Resource.id).where(Resource.is_perishable == True)  # noqa: E712
    )
    perishable_ids = list(result.scalars().all())

    if not perishable_ids:
        return {"items_processed": 0, "total_qty_lost": 0}

    # Get all inventories with perishable resources that have quantity > 0
    result = await session.execute(
        select(Inventory.id).where(
            Inventory.resource_id.in_(perishable_ids),
            Inventory.quantity > 0,
        )
    )
    inv_ids = list(result.scalars().all())

    total_lost = 0
    processed = 0

    for inv_id in inv_ids:
        try:
            r = await settle_inventory_decay(session, inv_id, now=now)
            total_lost += r["qty_lost"]
            processed += 1
        except Exception:
            logger.exception("Failed to settle decay for inventory %d", inv_id)

    return {
        "items_processed": processed,
        "total_qty_lost": total_lost,
    }
