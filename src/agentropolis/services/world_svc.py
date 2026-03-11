"""World service - region queries, pathfinding, travel.

Provides:
- Region info queries
- Dijkstra shortest path between regions
- Agent travel initiation and arrival settlement
- Carry capacity validation (#48)
"""

import heapq
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from sqlalchemy.ext.asyncio import AsyncSession

from agentropolis.config import settings
from agentropolis.models import Agent, AgentSkill, Inventory, Region, RegionConnection, TravelQueue
from agentropolis.services.event_svc import get_effective_region_coefficients
from agentropolis.services.training_hooks import get_travel_time_modifier, log_travel_decision


def _coerce_now(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(UTC)
    if now.tzinfo is None:
        return now.replace(tzinfo=UTC)
    return now


def _serialize_region(region: Region) -> dict:
    connections = sorted(
        region.connections_from,
        key=lambda connection: (connection.travel_time_seconds, connection.to_region_id),
    )
    return {
        "region_id": region.id,
        "name": region.name,
        "safety_tier": region.safety_tier.value,
        "region_type": region.region_type.value,
        "price_coefficient": float(region.price_coefficient),
        "tax_rate": float(region.tax_rate),
        "treasury": int(region.treasury),
        "resource_specializations": region.resource_specializations or {},
        "description": region.description or "",
        "connections": [
            {
                "to_region_id": connection.to_region_id,
                "travel_time_seconds": connection.travel_time_seconds,
                "terrain_type": connection.terrain_type,
                "is_portal": connection.is_portal,
                "danger_level": connection.danger_level,
            }
            for connection in connections
        ],
    }


def _serialize_travel(travel: TravelQueue) -> dict:
    return {
        "agent_id": travel.agent_id,
        "from_region_id": travel.from_region_id,
        "to_region_id": travel.to_region_id,
        "departed_at": travel.departed_at.isoformat() if travel.departed_at else None,
        "arrives_at": travel.arrives_at.isoformat() if travel.arrives_at else None,
        "cargo": travel.cargo or {},
        "in_transit": True,
    }


def _normalize_timestamp(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


async def _get_agent_strength_level(session: AsyncSession, agent_id: int) -> int:
    result = await session.execute(
        select(AgentSkill.level).where(
            AgentSkill.agent_id == agent_id,
            AgentSkill.skill_name == "Strength",
        )
    )
    level = result.scalar_one_or_none()
    return int(level or 0)


async def _merge_agent_inventory_region(
    session: AsyncSession,
    *,
    agent_id: int,
    from_region_id: int,
    to_region_id: int,
) -> None:
    result = await session.execute(
        select(Inventory)
        .where(
            Inventory.agent_id == agent_id,
            Inventory.company_id.is_(None),
            Inventory.region_id == from_region_id,
        )
        .with_for_update()
    )
    source_rows = list(result.scalars().all())

    for source in source_rows:
        dest_result = await session.execute(
            select(Inventory)
            .where(
                Inventory.agent_id == agent_id,
                Inventory.company_id.is_(None),
                Inventory.region_id == to_region_id,
                Inventory.resource_id == source.resource_id,
            )
            .with_for_update()
        )
        destination = dest_result.scalar_one_or_none()
        if destination is None:
            source.region_id = to_region_id
            continue

        destination.quantity = int(destination.quantity or 0) + int(source.quantity or 0)
        destination.reserved = int(destination.reserved or 0) + int(source.reserved or 0)
        await session.delete(source)


async def _settle_due_agent_travel(
    session: AsyncSession,
    *,
    agent_id: int,
    now: datetime,
) -> bool:
    result = await session.execute(
        select(TravelQueue)
        .where(TravelQueue.agent_id == agent_id)
        .with_for_update()
    )
    travel = result.scalar_one_or_none()
    if travel is None:
        return False

    arrives_at = _normalize_timestamp(travel.arrives_at)
    if arrives_at > now:
        return False

    agent_result = await session.execute(
        select(Agent).where(Agent.id == travel.agent_id).with_for_update()
    )
    agent = agent_result.scalar_one_or_none()
    if agent is not None:
        agent.current_region_id = travel.to_region_id
        agent.last_active_at = now
        await _merge_agent_inventory_region(
            session,
            agent_id=travel.agent_id,
            from_region_id=travel.from_region_id,
            to_region_id=travel.to_region_id,
        )

    await session.delete(travel)
    await session.flush()
    return True


def calculate_carry_capacity(strength_level: int = 0) -> int:
    """Calculate agent's carry capacity in kg.

    Base 50kg + Strength skill x 10kg/level.
    """
    return settings.AGENT_BASE_CARRY_KG + strength_level * settings.AGENT_CARRY_PER_STRENGTH_LEVEL


async def get_region(session: AsyncSession, region_id: int) -> dict:
    """Get region info."""
    result = await session.execute(
        select(Region)
        .options(selectinload(Region.connections_from))
        .where(Region.id == region_id)
    )
    region = result.scalar_one_or_none()
    if region is None:
        raise ValueError(f"Region {region_id} not found")
    return _serialize_region(region)


async def get_all_regions(session: AsyncSession) -> list[dict]:
    """Get all regions with connections."""
    result = await session.execute(
        select(Region).options(selectinload(Region.connections_from)).order_by(Region.id)
    )
    return [_serialize_region(region) for region in result.scalars().all()]


async def find_path(
    session: AsyncSession, from_region_id: int, to_region_id: int
) -> dict:
    """Find shortest path between two regions using Dijkstra.

    Returns: {"path": [region_ids], "total_time_seconds": int}
    """
    if from_region_id == to_region_id:
        return {"path": [from_region_id], "total_time_seconds": 0}

    region_ids_result = await session.execute(select(Region.id))
    region_ids = set(region_ids_result.scalars().all())
    if from_region_id not in region_ids:
        raise ValueError(f"Region {from_region_id} not found")
    if to_region_id not in region_ids:
        raise ValueError(f"Region {to_region_id} not found")

    result = await session.execute(select(RegionConnection))
    adjacency: dict[int, list[tuple[int, int]]] = {}
    for connection in result.scalars().all():
        adjacency.setdefault(connection.from_region_id, []).append(
            (connection.to_region_id, connection.travel_time_seconds)
        )

    distances: dict[int, int] = {from_region_id: 0}
    previous: dict[int, int | None] = {from_region_id: None}
    queue: list[tuple[int, int]] = [(0, from_region_id)]

    while queue:
        current_distance, current_region = heapq.heappop(queue)
        if current_region == to_region_id:
            break
        if current_distance > distances.get(current_region, current_distance):
            continue

        for neighbor, edge_cost in adjacency.get(current_region, []):
            next_distance = current_distance + edge_cost
            if next_distance < distances.get(neighbor, 2**31 - 1):
                distances[neighbor] = next_distance
                previous[neighbor] = current_region
                heapq.heappush(queue, (next_distance, neighbor))

    if to_region_id not in distances:
        raise ValueError(f"No path from region {from_region_id} to {to_region_id}")

    path: list[int] = []
    cursor: int | None = to_region_id
    while cursor is not None:
        path.append(cursor)
        cursor = previous.get(cursor)
    path.reverse()

    return {
        "path": path,
        "total_time_seconds": distances[to_region_id],
    }


async def start_travel(
    session: AsyncSession, agent_id: int, to_region_id: int, now: datetime | None = None
) -> dict:
    """Initiate agent travel to a region.

    Validates carry capacity before allowing travel.
    Returns: {"from_region_id", "to_region_id", "departed_at", "arrives_at"}
    """
    now = _coerce_now(now)
    await _settle_due_agent_travel(session, agent_id=agent_id, now=now)

    result = await session.execute(
        select(Agent).where(Agent.id == agent_id).with_for_update()
    )
    agent = result.scalar_one_or_none()
    if agent is None:
        raise ValueError(f"Agent {agent_id} not found")
    if not agent.is_alive:
        raise ValueError(f"Agent {agent_id} is dead and cannot travel")
    if agent.current_region_id == to_region_id:
        raise ValueError("Agent is already in the destination region")

    existing = await session.execute(
        select(TravelQueue)
        .where(TravelQueue.agent_id == agent_id)
        .with_for_update()
    )
    if existing.scalar_one_or_none() is not None:
        raise ValueError(f"Agent {agent_id} is already traveling")

    path_info = await find_path(session, agent.current_region_id, to_region_id)

    inventory_result = await session.execute(
        select(Inventory).where(
            Inventory.agent_id == agent_id,
            Inventory.company_id.is_(None),
            Inventory.region_id == agent.current_region_id,
        )
    )
    carried_rows = inventory_result.scalars().all()
    carried_weight = sum(int(row.quantity or 0) for row in carried_rows)
    strength_level = await _get_agent_strength_level(session, agent_id)
    carry_capacity = calculate_carry_capacity(strength_level)
    if carried_weight > carry_capacity:
        raise ValueError(
            f"Travel blocked by carry capacity: {carried_weight:.1f}kg > {carry_capacity}kg"
        )

    travel_time_modifier = await get_travel_time_modifier(session, agent_id)
    region_coefficients = await get_effective_region_coefficients(
        session,
        agent.current_region_id,
        now=now,
    )
    adjusted_travel_seconds = max(
        1,
        int(
            round(
                path_info["total_time_seconds"]
                * travel_time_modifier
                * float(region_coefficients.get("travel_time_modifier", 1.0))
            )
        ),
    )

    travel = TravelQueue(
        agent_id=agent_id,
        from_region_id=agent.current_region_id,
        to_region_id=to_region_id,
        departed_at=now,
        arrives_at=now + timedelta(seconds=adjusted_travel_seconds),
        cargo={
            str(row.resource_id): int(row.quantity or 0)
            for row in carried_rows
            if int(row.quantity or 0) > 0
        },
    )
    session.add(travel)
    agent.last_active_at = now

    await log_travel_decision(
        session,
        agent_id,
        from_region_id=travel.from_region_id,
        to_region_id=to_region_id,
        travel_time_seconds=adjusted_travel_seconds,
    )
    await session.flush()
    return _serialize_travel(travel)


async def settle_travel_arrivals(
    session: AsyncSession, now: datetime | None = None
) -> int:
    """Settle all completed travels. Returns count of arrivals."""
    now = _coerce_now(now)
    result = await session.execute(
        select(TravelQueue)
        .where(TravelQueue.arrives_at <= now)
        .with_for_update()
    )
    travels = list(result.scalars().all())

    settled = 0
    for travel in travels:
        if await _settle_due_agent_travel(session, agent_id=travel.agent_id, now=now):
            settled += 1

    return settled


async def get_travel_status(session: AsyncSession, agent_id: int) -> dict | None:
    """Get current travel status for an agent, or None if not traveling."""
    now = _coerce_now()
    await _settle_due_agent_travel(session, agent_id=agent_id, now=now)

    result = await session.execute(
        select(TravelQueue).where(TravelQueue.agent_id == agent_id)
    )
    travel = result.scalar_one_or_none()
    if travel is None:
        return None
    return _serialize_travel(travel)
