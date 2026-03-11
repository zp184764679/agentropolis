"""Career path service.

Career paths give permanent bonuses to specific activities:
- MINER: +20% gathering XP
- ARTISAN: +20% crafting XP
- MERCHANT: -10% trade tax
- SOLDIER: +15% combat power
- DIPLOMAT: +50% reputation gain
"""

import enum
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentropolis.models.agent import Agent

logger = logging.getLogger(__name__)


class CareerPath(enum.StrEnum):
    MINER = "miner"
    ARTISAN = "artisan"
    MERCHANT = "merchant"
    SOLDIER = "soldier"
    DIPLOMAT = "diplomat"


CAREER_BONUSES: dict[str, dict[str, float]] = {
    "miner": {"gathering_xp_bonus": 0.20},
    "artisan": {"crafting_xp_bonus": 0.20},
    "merchant": {"trade_tax_reduction": 0.10},
    "soldier": {"combat_power_bonus": 0.15},
    "diplomat": {"reputation_gain_bonus": 0.50},
}


async def set_career(
    session: AsyncSession,
    agent_id: int,
    career_path: str,
) -> dict:
    """Set or change an agent's career path.

    Returns: {"agent_id", "career_path", "bonuses"}
    Raises: ValueError if invalid career path
    """
    try:
        career = CareerPath(career_path)
    except ValueError as err:
        valid = [c.value for c in CareerPath]
        raise ValueError(f"Invalid career path: {career_path}. Valid: {valid}") from err

    result = await session.execute(
        select(Agent).where(Agent.id == agent_id).with_for_update()
    )
    agent = result.scalar_one_or_none()
    if agent is None:
        raise ValueError(f"Agent {agent_id} not found")

    agent.career_path = career.value
    await session.flush()

    return {
        "agent_id": agent_id,
        "career_path": career.value,
        "bonuses": CAREER_BONUSES[career.value],
    }


def get_career_bonuses(career_path: str | None) -> dict[str, float]:
    """Get bonuses for a career path. Returns empty dict if no career."""
    if career_path is None:
        return {}
    return CAREER_BONUSES.get(career_path, {})


def get_career_xp_multiplier(career_path: str | None, skill_category: str) -> float:
    """Get XP multiplier for a skill category based on career path.

    Returns: multiplier (1.0 = no bonus)
    """
    if career_path is None:
        return 1.0

    bonuses = CAREER_BONUSES.get(career_path, {})

    if career_path == "miner" and skill_category == "gathering":
        return 1.0 + bonuses.get("gathering_xp_bonus", 0.0)
    elif career_path == "artisan" and skill_category == "crafting":
        return 1.0 + bonuses.get("crafting_xp_bonus", 0.0)

    return 1.0


def get_career_tax_reduction(career_path: str | None) -> float:
    """Get trade tax reduction from career. Returns 0.0 if no reduction."""
    if career_path == "merchant":
        return CAREER_BONUSES["merchant"].get("trade_tax_reduction", 0.0)
    return 0.0


def get_career_combat_modifier(career_path: str | None) -> float:
    """Get combat power multiplier from career path."""
    if career_path == "soldier":
        return 1.0 + CAREER_BONUSES["soldier"].get("combat_power_bonus", 0.0)
    return 1.0


def get_career_reputation_gain_multiplier(career_path: str | None) -> float:
    """Get multiplier for positive reputation changes."""
    if career_path == "diplomat":
        return 1.0 + CAREER_BONUSES["diplomat"].get("reputation_gain_bonus", 0.0)
    return 1.0
