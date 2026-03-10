"""Diplomacy service - agent relationships and treaties."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from agentropolis.models import (
    Agent,
    AgentRelationship,
    Guild,
    GuildMember,
    GuildRank,
    RelationType,
    Treaty,
    TreatyType,
)
from agentropolis.services.training_hooks import log_diplomacy_decision


def _coerce_now(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(UTC)
    if now.tzinfo is None:
        return now.replace(tzinfo=UTC)
    return now


def _clamp_trust(value: int) -> int:
    return max(-100, min(100, int(value)))


def _serialize_relationship(
    relationship: AgentRelationship | None,
    *,
    agent_id: int,
    target_agent_id: int,
) -> dict:
    if relationship is None:
        return {
            "agent_id": agent_id,
            "target_agent_id": target_agent_id,
            "relation_type": RelationType.NEUTRAL.value,
            "trust_score": 0,
        }
    return {
        "agent_id": relationship.agent_id,
        "target_agent_id": relationship.target_agent_id,
        "relation_type": relationship.relation_type.value,
        "trust_score": int(relationship.trust_score),
    }


def _serialize_treaty(treaty: Treaty) -> dict:
    return {
        "treaty_id": treaty.id,
        "treaty_type": treaty.treaty_type.value,
        "party_a_agent_id": treaty.party_a_agent_id,
        "party_a_guild_id": treaty.party_a_guild_id,
        "party_b_agent_id": treaty.party_b_agent_id,
        "party_b_guild_id": treaty.party_b_guild_id,
        "terms": treaty.terms or {},
        "is_active": bool(treaty.is_active),
        "expires_at": treaty.expires_at.isoformat() if treaty.expires_at else None,
    }


async def _require_agent(session: AsyncSession, agent_id: int) -> Agent:
    result = await session.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if agent is None:
        raise ValueError(f"Agent {agent_id} not found")
    return agent


async def _require_guild(session: AsyncSession, guild_id: int) -> Guild:
    result = await session.execute(select(Guild).where(Guild.id == guild_id))
    guild = result.scalar_one_or_none()
    if guild is None:
        raise ValueError(f"Guild {guild_id} not found")
    return guild


async def _ensure_treaty_party_exists(
    session: AsyncSession,
    *,
    agent_id: int | None,
    guild_id: int | None,
    label: str,
) -> None:
    if (agent_id is None) == (guild_id is None):
        raise ValueError(f"{label} must specify exactly one of agent_id or guild_id")
    if agent_id is not None:
        await _require_agent(session, agent_id)
    if guild_id is not None:
        guild = await _require_guild(session, guild_id)
        if not guild.is_active:
            raise ValueError(f"Guild {guild_id} is inactive")


async def _agent_can_represent_guild(
    session: AsyncSession,
    *,
    agent_id: int,
    guild_id: int,
) -> bool:
    result = await session.execute(
        select(GuildMember).where(
            GuildMember.guild_id == guild_id,
            GuildMember.agent_id == agent_id,
            GuildMember.rank.in_([GuildRank.LEADER, GuildRank.OFFICER]),
        )
    )
    return result.scalar_one_or_none() is not None


async def get_relationship(
    session: AsyncSession, agent_id: int, target_agent_id: int
) -> dict:
    """Get relationship between two agents."""
    result = await session.execute(
        select(AgentRelationship).where(
            AgentRelationship.agent_id == agent_id,
            AgentRelationship.target_agent_id == target_agent_id,
        )
    )
    relationship = result.scalar_one_or_none()
    return _serialize_relationship(
        relationship,
        agent_id=agent_id,
        target_agent_id=target_agent_id,
    )


async def set_relationship(
    session: AsyncSession,
    agent_id: int,
    target_agent_id: int,
    relation_type: str,
    trust_delta: int = 0,
) -> dict:
    """Set relationship between two agents."""
    if agent_id == target_agent_id:
        raise ValueError("Agents cannot set relationships to themselves")

    await _require_agent(session, agent_id)
    await _require_agent(session, target_agent_id)

    result = await session.execute(
        select(AgentRelationship)
        .where(
            AgentRelationship.agent_id == agent_id,
            AgentRelationship.target_agent_id == target_agent_id,
        )
        .with_for_update()
    )
    relationship = result.scalar_one_or_none()
    if relationship is None:
        relationship = AgentRelationship(
            agent_id=agent_id,
            target_agent_id=target_agent_id,
            trust_score=0,
        )
        session.add(relationship)

    relationship.relation_type = RelationType(relation_type)
    relationship.trust_score = _clamp_trust(
        int(relationship.trust_score or 0) + trust_delta
    )
    await session.flush()

    await log_diplomacy_decision(
        session,
        agent_id,
        action="set_relationship",
        target_agent_id=target_agent_id,
        detail=f"{relationship.relation_type.value}:{relationship.trust_score}",
    )
    return _serialize_relationship(
        relationship,
        agent_id=agent_id,
        target_agent_id=target_agent_id,
    )


async def get_relationships(session: AsyncSession, agent_id: int) -> list[dict]:
    """Get all relationships for an agent."""
    result = await session.execute(
        select(AgentRelationship)
        .where(AgentRelationship.agent_id == agent_id)
        .order_by(AgentRelationship.target_agent_id)
    )
    return [
        _serialize_relationship(
            relationship,
            agent_id=relationship.agent_id,
            target_agent_id=relationship.target_agent_id,
        )
        for relationship in result.scalars().all()
    ]


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
    now = _coerce_now()
    await _ensure_treaty_party_exists(
        session,
        agent_id=party_a_agent_id,
        guild_id=party_a_guild_id,
        label="party_a",
    )
    await _ensure_treaty_party_exists(
        session,
        agent_id=party_b_agent_id,
        guild_id=party_b_guild_id,
        label="party_b",
    )

    if party_a_agent_id is not None and party_b_agent_id == party_a_agent_id:
        raise ValueError("Treaty target must be different from proposer")
    if party_a_guild_id is not None and party_b_guild_id == party_a_guild_id:
        raise ValueError("Treaty target guild must be different from proposer guild")

    treaty = Treaty(
        party_a_agent_id=party_a_agent_id,
        party_a_guild_id=party_a_guild_id,
        party_b_agent_id=party_b_agent_id,
        party_b_guild_id=party_b_guild_id,
        treaty_type=TreatyType(treaty_type),
        terms=terms or {},
        is_active=False,
        expires_at=(
            now + timedelta(hours=duration_hours)
            if duration_hours is not None
            else None
        ),
    )
    session.add(treaty)
    await session.flush()

    if party_a_agent_id is not None:
        await log_diplomacy_decision(
            session,
            party_a_agent_id,
            action="propose_treaty",
            target_agent_id=party_b_agent_id,
            detail=f"{treaty.treaty_type.value} #{treaty.id}",
            treaty_id=treaty.id,
        )
    return _serialize_treaty(treaty)


async def accept_treaty(session: AsyncSession, treaty_id: int, agent_id: int) -> dict:
    """Accept a proposed treaty."""
    await _require_agent(session, agent_id)

    result = await session.execute(
        select(Treaty).where(Treaty.id == treaty_id).with_for_update()
    )
    treaty = result.scalar_one_or_none()
    if treaty is None:
        raise ValueError(f"Treaty {treaty_id} not found")
    if treaty.is_active:
        raise ValueError(f"Treaty {treaty_id} is already active")

    if treaty.party_b_agent_id is not None:
        if treaty.party_b_agent_id != agent_id:
            raise ValueError("Only the target agent can accept this treaty")
    elif treaty.party_b_guild_id is not None:
        can_accept = await _agent_can_represent_guild(
            session,
            agent_id=agent_id,
            guild_id=treaty.party_b_guild_id,
        )
        if not can_accept:
            raise ValueError("Only a guild leader or officer can accept this treaty")
    else:
        raise ValueError("Treaty has no valid counterparty")

    treaty.is_active = True

    if treaty.party_a_agent_id is not None and treaty.party_b_agent_id is not None:
        relation_type = (
            RelationType.ALLIED
            if treaty.treaty_type in {TreatyType.ALLIANCE, TreatyType.MUTUAL_DEFENSE}
            else RelationType.FRIENDLY
        )
        await set_relationship(
            session,
            treaty.party_a_agent_id,
            treaty.party_b_agent_id,
            relation_type.value,
            trust_delta=10,
        )
        await set_relationship(
            session,
            treaty.party_b_agent_id,
            treaty.party_a_agent_id,
            relation_type.value,
            trust_delta=10,
        )

    await log_diplomacy_decision(
        session,
        agent_id,
        action="accept_treaty",
        target_agent_id=treaty.party_a_agent_id,
        detail=f"{treaty.treaty_type.value} #{treaty.id}",
        treaty_id=treaty.id,
    )
    await session.flush()
    return _serialize_treaty(treaty)


async def get_treaties(
    session: AsyncSession,
    agent_id: int | None = None,
    guild_id: int | None = None,
    active_only: bool = True,
) -> list[dict]:
    if agent_id is None and guild_id is None:
        raise ValueError("agent_id or guild_id is required")

    query = select(Treaty).order_by(Treaty.created_at.desc())
    filters = []
    if agent_id is not None:
        filters.append(
            or_(
                Treaty.party_a_agent_id == agent_id,
                Treaty.party_b_agent_id == agent_id,
            )
        )
    if guild_id is not None:
        filters.append(
            or_(
                Treaty.party_a_guild_id == guild_id,
                Treaty.party_b_guild_id == guild_id,
            )
        )

    query = query.where(or_(*filters))
    if active_only:
        query = query.where(Treaty.is_active.is_(True))

    result = await session.execute(query)
    return [_serialize_treaty(treaty) for treaty in result.scalars().all()]


async def expire_treaties(
    session: AsyncSession,
    now: datetime | None = None,
) -> int:
    """Expire all treaties past their expiration. Returns count expired."""
    now = _coerce_now(now)
    result = await session.execute(
        select(Treaty)
        .where(
            Treaty.is_active.is_(True),
            Treaty.expires_at.is_not(None),
            Treaty.expires_at <= now,
        )
        .with_for_update()
    )
    treaties = result.scalars().all()
    for treaty in treaties:
        treaty.is_active = False

    await session.flush()
    return len(treaties)
