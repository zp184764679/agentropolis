"""Building natural decay service.

Buildings lose durability over time independent of combat damage.
durability -= BUILDING_NATURAL_DECAY_PER_HOUR * elapsed_hours
durability=0 → DISABLED
"""

import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentropolis.config import settings
from agentropolis.models.building import Building, BuildingStatus

logger = logging.getLogger(__name__)


async def settle_building_decay(
    session: AsyncSession,
    building_id: int,
    now: datetime | None = None,
) -> dict:
    """Apply natural decay to a single building.

    Returns: {"building_id", "old_durability", "new_durability", "status"}
    """
    if now is None:
        now = datetime.now(UTC)

    result = await session.execute(
        select(Building).where(Building.id == building_id).with_for_update()
    )
    building = result.scalar_one_or_none()
    if building is None:
        raise ValueError(f"Building {building_id} not found")

    if building.durability <= 0:
        return {
            "building_id": building_id,
            "old_durability": 0.0,
            "new_durability": 0.0,
            "status": building.status.value,
        }

    # Use updated_at as reference for decay timing
    last_check = building.updated_at if building.updated_at else now
    elapsed_hours = (now - last_check).total_seconds() / 3600.0

    if elapsed_hours <= 0:
        return {
            "building_id": building_id,
            "old_durability": building.durability,
            "new_durability": building.durability,
            "status": building.status.value,
        }

    old_durability = building.durability
    decay = settings.BUILDING_NATURAL_DECAY_PER_HOUR * elapsed_hours
    building.durability = max(0.0, building.durability - decay)

    # Disable if durability reaches 0
    if building.durability <= 0:
        building.durability = 0.0
        building.status = BuildingStatus.DISABLED

    await session.flush()

    return {
        "building_id": building_id,
        "old_durability": old_durability,
        "new_durability": building.durability,
        "status": building.status.value,
    }


async def settle_all_building_decay(
    session: AsyncSession,
    now: datetime | None = None,
) -> dict:
    """Apply natural decay to all buildings. Housekeeping task.

    Returns: {"buildings_processed", "buildings_disabled"}
    """
    if now is None:
        now = datetime.now(UTC)

    result = await session.execute(
        select(Building.id).where(Building.durability > 0)
    )
    building_ids = list(result.scalars().all())

    processed = 0
    disabled = 0

    for bid in building_ids:
        try:
            r = await settle_building_decay(session, bid, now=now)
            processed += 1
            if r["new_durability"] <= 0:
                disabled += 1
        except Exception:
            logger.exception("Failed to settle decay for building %d", bid)

    return {
        "buildings_processed": processed,
        "buildings_disabled": disabled,
    }
