"""World event service - dynamic world events with mechanical effects."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import random

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentropolis.models.region import Region
from agentropolis.models.world_event import WorldEvent

_EVENT_TEMPLATES = [
    {
        "event_type": "trade_fair",
        "description": "A regional trade fair improves liquidity and merchant activity.",
        "effects": {"price_modifier": 1.05, "tax_modifier": 1.0, "production_modifier": 1.0},
    },
    {
        "event_type": "supply_disruption",
        "description": "Logistical disruption drives prices upward and slows movement.",
        "effects": {"price_modifier": 1.1, "travel_time_modifier": 1.15},
    },
    {
        "event_type": "harvest_boom",
        "description": "A local boom improves productive output and stability.",
        "effects": {"production_modifier": 1.1, "price_modifier": 0.97},
    },
]


def _coerce_now(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(UTC)
    if now.tzinfo is None:
        return now.replace(tzinfo=UTC)
    return now


def _serialize_event(event: WorldEvent) -> dict:
    return {
        "event_id": event.id,
        "event_type": event.event_type,
        "region_id": event.region_id,
        "description": event.description,
        "effects": event.effects or {},
        "starts_at": event.starts_at.isoformat() if event.starts_at else None,
        "ends_at": event.ends_at.isoformat() if event.ends_at else None,
        "is_active": bool(event.is_active),
    }


async def generate_random_event(
    session: AsyncSession, now: datetime | None = None
) -> dict | None:
    """Generate a random world event (best-effort, low frequency)."""
    timestamp = _coerce_now(now)
    roll = random.random()
    if roll >= 0.1:
        return None

    regions = (
        await session.execute(select(Region).order_by(Region.id.asc()))
    ).scalars().all()
    if not regions:
        return None

    region = random.choice(list(regions))
    template = random.choice(_EVENT_TEMPLATES)
    event = WorldEvent(
        event_type=template["event_type"],
        region_id=region.id,
        effects=template["effects"],
        description=template["description"],
        starts_at=timestamp,
        ends_at=timestamp + timedelta(hours=6),
        is_active=True,
    )
    session.add(event)
    await session.flush()
    return _serialize_event(event)


async def get_active_events(session: AsyncSession) -> list[dict]:
    """Get all currently active world events."""
    now = _coerce_now()
    result = await session.execute(
        select(WorldEvent)
        .where(
            WorldEvent.is_active.is_(True),
            WorldEvent.ends_at > now,
        )
        .order_by(WorldEvent.ends_at.asc(), WorldEvent.id.asc())
    )
    return [_serialize_event(event) for event in result.scalars().all()]


async def expire_events(session: AsyncSession) -> int:
    """Expire events past their end time. Returns count expired."""
    now = _coerce_now()
    result = await session.execute(
        select(WorldEvent)
        .where(
            WorldEvent.is_active.is_(True),
            WorldEvent.ends_at <= now,
        )
        .with_for_update()
    )
    events = result.scalars().all()
    for event in events:
        event.is_active = False
    await session.flush()
    return len(list(events))


async def get_region_events(session: AsyncSession, region_id: int) -> list[dict]:
    """Get active events affecting a specific region."""
    now = _coerce_now()
    result = await session.execute(
        select(WorldEvent)
        .where(
            WorldEvent.region_id == region_id,
            WorldEvent.is_active.is_(True),
            WorldEvent.ends_at > now,
        )
        .order_by(WorldEvent.ends_at.asc(), WorldEvent.id.asc())
    )
    return [_serialize_event(event) for event in result.scalars().all()]


async def get_effective_region_coefficients(
    session: AsyncSession,
    region_id: int,
    now: datetime | None = None,
) -> dict:
    """Get effective region coefficients after applying active event modifiers."""
    if now is None:
        now = datetime.now(UTC)

    result = await session.execute(select(Region).where(Region.id == region_id))
    region = result.scalar_one_or_none()
    if region is None:
        raise ValueError(f"Region {region_id} not found")

    coefficients = {
        "price_coefficient": region.price_coefficient,
        "tax_rate": region.tax_rate,
        "production_modifier": 1.0,
        "travel_time_modifier": 1.0,
    }

    result = await session.execute(
        select(WorldEvent).where(
            WorldEvent.region_id == region_id,
            WorldEvent.is_active.is_(True),
            WorldEvent.ends_at > now,
        )
    )
    events = result.scalars().all()

    for event in events:
        effects = event.effects or {}
        if "price_modifier" in effects:
            coefficients["price_coefficient"] *= effects["price_modifier"]
        if "tax_modifier" in effects:
            coefficients["tax_rate"] *= effects["tax_modifier"]
        if "production_modifier" in effects:
            coefficients["production_modifier"] *= effects["production_modifier"]
        if "travel_time_modifier" in effects:
            coefficients["travel_time_modifier"] *= effects["travel_time_modifier"]

    return coefficients
