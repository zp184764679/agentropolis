"""Skill service - XP tracking, level-up, efficiency bonuses."""

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agentropolis.models import AgentSkill, SkillDefinition
from agentropolis.services.training_hooks import get_xp_modifier


def _coerce_now() -> datetime:
    return datetime.now(UTC)


def _level_requirement(skill: SkillDefinition, level: int) -> int:
    xp_per_level = skill.xp_per_level or {}
    explicit = xp_per_level.get(str(level)) if isinstance(xp_per_level, dict) else None
    if explicit is None and isinstance(xp_per_level, dict):
        explicit = xp_per_level.get(level)
    if explicit is not None:
        return max(1, int(explicit))

    base = 100
    if isinstance(xp_per_level, dict):
        base = int(xp_per_level.get("base", base))
    return max(1, base * level)


def _derive_level(total_xp: int, skill: SkillDefinition) -> int:
    remaining_xp = max(0, int(total_xp))
    level = 1

    while remaining_xp >= _level_requirement(skill, level):
        remaining_xp -= _level_requirement(skill, level)
        level += 1

    return level


def _serialize_agent_skill(skill: AgentSkill) -> dict:
    return {
        "skill_name": skill.skill_name,
        "level": skill.level,
        "xp": skill.xp,
        "last_practiced_at": (
            skill.last_practiced_at.isoformat() if skill.last_practiced_at else None
        ),
    }


async def award_xp(
    session: AsyncSession, agent_id: int, skill_name: str, xp_amount: int
) -> dict:
    """Award XP to an agent's skill. Creates skill entry if needed.

    Returns: {"skill_name", "new_xp", "new_level", "leveled_up": bool}
    """
    if xp_amount <= 0:
        raise ValueError("xp_amount must be greater than 0")

    result = await session.execute(
        select(SkillDefinition).where(func.lower(SkillDefinition.name) == skill_name.lower())
    )
    definition = result.scalar_one_or_none()
    if definition is None:
        raise ValueError(f"Skill '{skill_name}' not found")

    skill_result = await session.execute(
        select(AgentSkill)
        .where(
            AgentSkill.agent_id == agent_id,
            AgentSkill.skill_name == definition.name,
        )
        .with_for_update()
    )
    agent_skill = skill_result.scalar_one_or_none()
    if agent_skill is None:
        agent_skill = AgentSkill(agent_id=agent_id, skill_name=definition.name, level=1, xp=0)
        session.add(agent_skill)
        await session.flush()

    xp_multiplier = await get_xp_modifier(session, agent_id, definition.name)
    adjusted_xp = max(1, int(round(xp_amount * xp_multiplier)))
    previous_level = agent_skill.level

    agent_skill.xp += adjusted_xp
    agent_skill.level = _derive_level(agent_skill.xp, definition)
    agent_skill.last_practiced_at = _coerce_now()
    await session.flush()

    return {
        "skill_name": agent_skill.skill_name,
        "new_xp": agent_skill.xp,
        "new_level": agent_skill.level,
        "leveled_up": agent_skill.level > previous_level,
        "xp_awarded": adjusted_xp,
    }


async def get_agent_skills(session: AsyncSession, agent_id: int) -> list[dict]:
    """Get all skills for an agent."""
    result = await session.execute(
        select(AgentSkill)
        .where(AgentSkill.agent_id == agent_id)
        .order_by(AgentSkill.skill_name)
    )
    return [_serialize_agent_skill(skill) for skill in result.scalars().all()]


async def get_skill_efficiency(
    session: AsyncSession, agent_id: int, skill_name: str
) -> float:
    """Get production efficiency bonus from skill level (1.0 = no bonus)."""
    result = await session.execute(
        select(AgentSkill).where(
            AgentSkill.agent_id == agent_id,
            AgentSkill.skill_name == skill_name,
        )
    )
    agent_skill = result.scalar_one_or_none()
    if agent_skill is None:
        return 1.0
    return round(1.0 + max(0, agent_skill.level - 1) * 0.05, 3)


async def get_all_skill_definitions(session: AsyncSession) -> list[dict]:
    """Get all skill definitions."""
    result = await session.execute(
        select(SkillDefinition).order_by(SkillDefinition.name)
    )
    return [
        {
            "skill_name": skill.name,
            "category": skill.category.value,
            "description": skill.description or "",
            "prerequisites": skill.prerequisites or {},
        }
        for skill in result.scalars().all()
    ]
