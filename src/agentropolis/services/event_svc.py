"""World event service - dynamic world events with mechanical effects.

Events can modify region coefficients (price, tax, production).
Other services should call get_effective_region_coefficients() instead
of reading region fields directly.
"""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentropolis.models.region import Region
from agentropolis.models.world_event import WorldEvent


async def generate_random_event(
    session: AsyncSession, now: datetime | None = None
) -> dict | None:
    """Generate a random world event (may return None if no event triggered).

    Returns: {"event_id", "event_type", "region_id", "description", "effects"} or None
    """
    raise NotImplementedError("Issue #29: Implement event service")


async def get_active_events(session: AsyncSession) -> list[dict]:
    """Get all currently active world events."""
    raise NotImplementedError("Issue #29: Implement event service")


async def expire_events(session: AsyncSession) -> int:
    """Expire events past their end time. Returns count expired."""
    raise NotImplementedError("Issue #29: Implement event service")


async def get_region_events(session: AsyncSession, region_id: int) -> list[dict]:
    """Get active events affecting a specific region."""
    raise NotImplementedError("Issue #29: Implement event service")


async def get_effective_region_coefficients(
    session: AsyncSession,
    region_id: int,
    now: datetime | None = None,
) -> dict:
    """Get effective region coefficients after applying active event modifiers.

    Other services (market, production, tax) should call this instead of
    reading region fields directly.

    Returns: {
        "price_coefficient": float,
        "tax_rate": float,
        "production_modifier": float,
        "travel_time_modifier": float,
    }
    """
    if now is None:
        now = datetime.now(UTC)

    # Get base region values
    result = await session.execute(
        select(Region).where(Region.id == region_id)
    )
    region = result.scalar_one_or_none()
    if region is None:
        raise ValueError(f"Region {region_id} not found")

    coefficients = {
        "price_coefficient": region.price_coefficient,
        "tax_rate": region.tax_rate,
        "production_modifier": 1.0,
        "travel_time_modifier": 1.0,
    }

    # Get active events for this region
    result = await session.execute(
        select(WorldEvent).where(
            WorldEvent.region_id == region_id,
            WorldEvent.is_active == True,  # noqa: E712
        )
    )
    events = result.scalars().all()

    # Apply event modifiers
    for event in events:
        if event.effects is None:
            continue

        effects = event.effects
        if "price_modifier" in effects:
            coefficients["price_coefficient"] *= effects["price_modifier"]
        if "tax_modifier" in effects:
            coefficients["tax_rate"] *= effects["tax_modifier"]
        if "production_modifier" in effects:
            coefficients["production_modifier"] *= effects["production_modifier"]
        if "travel_time_modifier" in effects:
            coefficients["travel_time_modifier"] *= effects["travel_time_modifier"]

    return coefficients
