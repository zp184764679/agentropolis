"""Diplomacy service - agent relationships and treaties."""

from sqlalchemy.ext.asyncio import AsyncSession


async def set_relationship(
    session: AsyncSession, agent_id: int, target_agent_id: int, relation_type: str
) -> dict:
    """Set relationship between two agents."""
    raise NotImplementedError("Issue #28: Implement diplomacy service")


async def get_relationships(session: AsyncSession, agent_id: int) -> list[dict]:
    """Get all relationships for an agent."""
    raise NotImplementedError("Issue #28: Implement diplomacy service")


async def propose_treaty(
    session: AsyncSession,
    treaty_type: str,
    *,
    party_a_agent_id: int | None = None,
    party_a_guild_id: int | None = None,
    party_b_agent_id: int | None = None,
    party_b_guild_id: int | None = None,
    terms: dict | None = None,
    duration_hours: int | None = None,
) -> dict:
    """Propose a treaty."""
    raise NotImplementedError("Issue #28: Implement diplomacy service")


async def accept_treaty(session: AsyncSession, treaty_id: int, agent_id: int) -> dict:
    """Accept a proposed treaty."""
    raise NotImplementedError("Issue #28: Implement diplomacy service")


async def expire_treaties(session: AsyncSession) -> int:
    """Expire all treaties past their expiration. Returns count expired."""
    raise NotImplementedError("Issue #28: Implement diplomacy service")
