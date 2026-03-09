"""Agent vitals service - lazy settlement of hunger/thirst/energy/health.

settle_agent_vitals(agent_id, now):
1. Load Agent (FOR UPDATE)
2. Compute elapsed = now - last_vitals_at
3. Decay hunger, thirst, energy based on elapsed time
4. If hunger=0 or thirst=0, apply health damage
5. Update last_vitals_at = now
"""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentropolis.config import settings
from agentropolis.models import Agent


def _coerce_now(now: datetime | None) -> datetime:
    if now is None:
        return datetime.now(UTC)
    if now.tzinfo is None:
        return now.replace(tzinfo=UTC)
    return now


def _clamp_vital(value: float) -> float:
    return max(0.0, min(100.0, float(value)))


def _serialize_agent(agent: Agent) -> dict:
    return {
        "hunger": round(float(agent.hunger), 3),
        "thirst": round(float(agent.thirst), 3),
        "energy": round(float(agent.energy), 3),
        "health": round(float(agent.health), 3),
        "is_alive": bool(agent.is_alive),
    }


async def settle_agent_vitals(
    session: AsyncSession, agent_id: int, now: datetime | None = None
) -> dict:
    """Settle vitals for a single agent.

    Returns: {"hunger", "thirst", "energy", "health", "is_alive"}
    """
    now = _coerce_now(now)

    result = await session.execute(
        select(Agent).where(Agent.id == agent_id).with_for_update()
    )
    agent = result.scalar_one_or_none()
    if agent is None:
        raise ValueError(f"Agent {agent_id} not found")

    last_vitals_at = agent.last_vitals_at
    if last_vitals_at is None:
        agent.last_vitals_at = now
        await session.flush()
        return _serialize_agent(agent)

    if last_vitals_at.tzinfo is None:
        last_vitals_at = last_vitals_at.replace(tzinfo=UTC)

    elapsed_seconds = max(0.0, (now - last_vitals_at).total_seconds())
    elapsed_hours = elapsed_seconds / 3600.0

    if elapsed_hours > 0:
        agent.hunger = _clamp_vital(
            float(agent.hunger) - settings.AGENT_HUNGER_DECAY_PER_HOUR * elapsed_hours
        )
        agent.thirst = _clamp_vital(
            float(agent.thirst) - settings.AGENT_THIRST_DECAY_PER_HOUR * elapsed_hours
        )
        agent.energy = _clamp_vital(
            float(agent.energy) - settings.AGENT_ENERGY_DECAY_PER_HOUR * elapsed_hours
        )

        health_decay = 0.0
        if agent.hunger <= 0:
            health_decay += (
                settings.AGENT_HEALTH_DECAY_WHEN_STARVING_PER_HOUR * elapsed_hours
            )
        if agent.thirst <= 0:
            health_decay += (
                settings.AGENT_HEALTH_DECAY_WHEN_DEHYDRATED_PER_HOUR * elapsed_hours
            )
        if health_decay > 0:
            agent.health = _clamp_vital(float(agent.health) - health_decay)

    if agent.health <= 0:
        agent.health = 0.0
        agent.is_alive = False
        agent.is_active = False

    agent.last_vitals_at = now
    await session.flush()
    return _serialize_agent(agent)


async def settle_all_agent_vitals(
    session: AsyncSession, now: datetime | None = None
) -> dict:
    """Settle vitals for all active agents. Used by housekeeping.

    Returns: {"agents_processed": int, "deaths": int}
    """
    now = _coerce_now(now)

    result = await session.execute(
        select(Agent.id, Agent.is_alive).where(Agent.is_active.is_(True))
    )
    rows = result.all()

    deaths = 0
    for agent_id, was_alive in rows:
        settled = await settle_agent_vitals(session, agent_id, now)
        if was_alive and not settled["is_alive"]:
            deaths += 1

    return {
        "agents_processed": len(rows),
        "deaths": deaths,
    }
