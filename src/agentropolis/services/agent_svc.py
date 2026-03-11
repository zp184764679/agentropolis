"""Agent service - registration, eat/drink/rest, death/respawn.

Handles agent lifecycle:
- Registration (generate API key, set starting region)
- Eat/drink/rest actions (replenish vitals from inventory)
- Death (vitals reach 0) and respawn (penalty)
"""

import secrets
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentropolis.api.auth import hash_api_key
from agentropolis.config import settings
from agentropolis.models import Agent, Inventory, Region, RegionType, Resource, StrategyProfile, TravelQueue
from agentropolis.services.agent_vitals import settle_agent_vitals
from agentropolis.services.inventory_svc import normalize_quantity_amount
from agentropolis.services.training_hooks import get_respawn_balance_modifier

AGENT_STARTER_INVENTORY: dict[str, int] = {
    "RAT": 8,
    "DW": 8,
}


def _coerce_now(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(UTC)
    if now.tzinfo is None:
        return now.replace(tzinfo=UTC)
    return now


def _clamp_vital(value: float) -> float:
    return max(0.0, min(100.0, float(value)))


def _serialize_agent_status(agent: Agent) -> dict:
    return {
        "agent_id": agent.id,
        "name": agent.name,
        "health": round(float(agent.health), 3),
        "hunger": round(float(agent.hunger), 3),
        "thirst": round(float(agent.thirst), 3),
        "energy": round(float(agent.energy), 3),
        "happiness": round(float(agent.happiness), 3),
        "reputation": round(float(agent.reputation), 3),
        "current_region_id": agent.current_region_id,
        "home_region_id": agent.home_region_id,
        "personal_balance": int(agent.personal_balance),
        "is_alive": bool(agent.is_alive),
        "career_path": agent.career_path,
    }


async def _get_agent_for_update(session: AsyncSession, agent_id: int) -> Agent:
    result = await session.execute(
        select(Agent).where(Agent.id == agent_id).with_for_update()
    )
    agent = result.scalar_one_or_none()
    if agent is None:
        raise ValueError(f"Agent {agent_id} not found")
    return agent


async def _resolve_home_region(
    session: AsyncSession, home_region_id: int | None
) -> Region:
    if home_region_id is not None:
        result = await session.execute(select(Region).where(Region.id == home_region_id))
        region = result.scalar_one_or_none()
        if region is None:
            raise ValueError(f"Region {home_region_id} not found")
        return region

    result = await session.execute(
        select(Region).where(Region.region_type == RegionType.CAPITAL).order_by(Region.id)
    )
    region = result.scalar_one_or_none()
    if region is not None:
        return region

    result = await session.execute(select(Region).order_by(Region.id))
    region = result.scalar_one_or_none()
    if region is None:
        raise ValueError("No regions available; seed_world() must run before registering agents")
    return region


async def _get_agent_inventory_row(
    session: AsyncSession,
    *,
    agent_id: int,
    region_id: int,
    resource: Resource,
) -> Inventory:
    result = await session.execute(
        select(Inventory)
        .where(
            Inventory.agent_id == agent_id,
            Inventory.company_id.is_(None),
            Inventory.region_id == region_id,
            Inventory.resource_id == resource.id,
        )
        .with_for_update()
    )
    inventory = result.scalar_one_or_none()
    if inventory is None:
        inventory = Inventory(
            agent_id=agent_id,
            region_id=region_id,
            resource_id=resource.id,
            quantity=0,
            reserved=0,
        )
        session.add(inventory)
        await session.flush()
    return inventory


async def _consume_vital_resource(
    session: AsyncSession,
    *,
    agent: Agent,
    resource_ticker: str,
    amount: int,
) -> Inventory:
    if amount <= 0:
        raise ValueError("amount must be greater than 0")

    result = await session.execute(
        select(Resource).where(Resource.ticker == resource_ticker)
    )
    resource = result.scalar_one_or_none()
    if resource is None:
        raise ValueError(f"Resource {resource_ticker} not found")

    inventory = await _get_agent_inventory_row(
        session,
        agent_id=agent.id,
        region_id=agent.current_region_id,
        resource=resource,
    )
    available = int(inventory.quantity or 0) - int(inventory.reserved or 0)
    if available < amount:
        raise ValueError(
            f"Insufficient {resource_ticker}: need {amount}, available {available}"
        )

    inventory.quantity = int(inventory.quantity or 0) - amount
    return inventory


async def register_agent(
    session: AsyncSession, name: str, home_region_id: int
) -> dict:
    """Register a new agent.

    Returns: {"agent_id", "api_key" (plaintext), "name", "home_region_id", "balance"}
    """
    now = _coerce_now()

    existing = await session.execute(select(Agent).where(Agent.name == name))
    if existing.scalar_one_or_none() is not None:
        raise ValueError(f"Agent name '{name}' is already taken")

    home_region = await _resolve_home_region(session, home_region_id)

    api_key = secrets.token_hex(settings.API_KEY_LENGTH)
    agent = Agent(
        name=name,
        api_key_hash=hash_api_key(api_key),
        current_region_id=home_region.id,
        home_region_id=home_region.id,
        personal_balance=settings.INITIAL_BALANCE,
        last_vitals_at=now,
        last_active_at=now,
    )
    session.add(agent)
    await session.flush()

    session.add(StrategyProfile(agent_id=agent.id))

    tickers = tuple(AGENT_STARTER_INVENTORY)
    resource_result = await session.execute(
        select(Resource).where(Resource.ticker.in_(tickers))
    )
    resources = {resource.ticker: resource for resource in resource_result.scalars().all()}
    missing = sorted(set(tickers) - set(resources))
    if missing:
        raise ValueError(f"Missing starter resources: {', '.join(missing)}")

    for ticker, quantity in AGENT_STARTER_INVENTORY.items():
        inventory = await _get_agent_inventory_row(
            session,
            agent_id=agent.id,
            region_id=home_region.id,
            resource=resources[ticker],
        )
        inventory.quantity = int(inventory.quantity or 0) + normalize_quantity_amount(quantity)

    await session.flush()

    return {
        "agent_id": agent.id,
        "name": agent.name,
        "api_key": api_key,
        "home_region_id": agent.home_region_id,
        "current_region_id": agent.current_region_id,
        "balance": int(agent.personal_balance),
    }


async def eat(session: AsyncSession, agent_id: int, amount: int = 1) -> dict:
    """Agent eats rations from inventory to replenish hunger."""
    now = _coerce_now()
    await settle_agent_vitals(session, agent_id, now)
    agent = await _get_agent_for_update(session, agent_id)
    if not agent.is_alive:
        raise ValueError(f"Agent {agent_id} is dead and cannot eat")

    inventory = await _consume_vital_resource(
        session,
        agent=agent,
        resource_ticker="RAT",
        amount=amount,
    )
    agent.hunger = _clamp_vital(
        float(agent.hunger) + settings.AGENT_EAT_HUNGER_RESTORE * amount
    )
    agent.last_active_at = now
    await session.flush()

    return {
        "agent_id": agent.id,
        "resource_ticker": "RAT",
        "consumed": amount,
        "remaining_quantity": int(inventory.quantity),
        "status": _serialize_agent_status(agent),
    }


async def drink(session: AsyncSession, agent_id: int, amount: int = 1) -> dict:
    """Agent drinks water from inventory to replenish thirst."""
    now = _coerce_now()
    await settle_agent_vitals(session, agent_id, now)
    agent = await _get_agent_for_update(session, agent_id)
    if not agent.is_alive:
        raise ValueError(f"Agent {agent_id} is dead and cannot drink")

    inventory = await _consume_vital_resource(
        session,
        agent=agent,
        resource_ticker="DW",
        amount=amount,
    )
    agent.thirst = _clamp_vital(
        float(agent.thirst) + settings.AGENT_DRINK_THIRST_RESTORE * amount
    )
    agent.last_active_at = now
    await session.flush()

    return {
        "agent_id": agent.id,
        "resource_ticker": "DW",
        "consumed": amount,
        "remaining_quantity": int(inventory.quantity),
        "status": _serialize_agent_status(agent),
    }


async def rest(session: AsyncSession, agent_id: int) -> dict:
    """Agent rests to replenish energy (time-based)."""
    now = _coerce_now()
    await settle_agent_vitals(session, agent_id, now)
    agent = await _get_agent_for_update(session, agent_id)
    if not agent.is_alive:
        raise ValueError(f"Agent {agent_id} is dead and cannot rest")

    agent.energy = _clamp_vital(
        float(agent.energy) + settings.AGENT_REST_ENERGY_RESTORE
    )
    agent.happiness = _clamp_vital(
        float(agent.happiness) + settings.AGENT_REST_HAPPINESS_RESTORE
    )
    agent.last_active_at = now
    await session.flush()

    return _serialize_agent_status(agent)


async def check_death(
    session: AsyncSession, agent_id: int, now: datetime | None = None
) -> bool:
    """Check if agent should die (health <= 0). Handle death if so."""
    settled = await settle_agent_vitals(session, agent_id, now)
    if settled["is_alive"]:
        return False

    result = await session.execute(
        select(TravelQueue).where(TravelQueue.agent_id == agent_id)
    )
    travel = result.scalar_one_or_none()
    if travel is not None:
        await session.delete(travel)
        await session.flush()

    return True


async def respawn(session: AsyncSession, agent_id: int) -> dict:
    """Respawn a dead agent at home region with penalty."""
    now = _coerce_now()
    agent = await _get_agent_for_update(session, agent_id)
    if agent.is_alive:
        raise ValueError(f"Agent {agent_id} is already alive")

    keep_bonus = await get_respawn_balance_modifier(session, agent_id)
    keep_fraction = min(
        1.0,
        max(0.0, (1.0 - settings.AGENT_RESPAWN_PENALTY) + keep_bonus),
    )
    balance_before = int(agent.personal_balance)
    agent.personal_balance = int(balance_before * keep_fraction)
    agent.current_region_id = agent.home_region_id
    agent.health = 100.0
    agent.hunger = 70.0
    agent.thirst = 70.0
    agent.energy = 80.0
    agent.happiness = max(float(agent.happiness), 40.0)
    agent.is_alive = True
    agent.is_active = True
    agent.last_vitals_at = now
    agent.last_active_at = now

    result = await session.execute(
        select(TravelQueue).where(TravelQueue.agent_id == agent_id)
    )
    travel = result.scalar_one_or_none()
    if travel is not None:
        await session.delete(travel)

    await session.flush()

    return {
        **_serialize_agent_status(agent),
        "balance_before": balance_before,
        "balance_after": int(agent.personal_balance),
    }


async def get_agent_status(
    session: AsyncSession, agent_id: int, now: datetime | None = None
) -> dict:
    """Get agent status with settled vitals."""
    await settle_agent_vitals(session, agent_id, now)
    result = await session.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if agent is None:
        raise ValueError(f"Agent {agent_id} not found")
    return _serialize_agent_status(agent)
