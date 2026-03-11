"""Guild service - guild management with level upgrades.

Guild Levels:
L1→L2: 500K copper + 10 NXC (unlocks guild warehouse)
L2→L3: 2M copper + 50 NXC (member tax reduction)
L3→L4: 5M copper + 100 NXC (guild shop discount)
"""

from datetime import UTC, datetime

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agentropolis.config import settings
from agentropolis.models import Agent, Guild, GuildMember, GuildRank, Region
from agentropolis.services.training_hooks import log_diplomacy_decision

GUILD_BASE_MAINTENANCE_COPPER = 10_000
GUILD_MEMBER_POWER = 1.8
GUILD_MEMBER_FACTOR = 10
GUILD_MAX_MEMBERS_PER_LEVEL = 20

# Guild upgrade costs: level → (copper, nxc)
GUILD_UPGRADE_COSTS: dict[int, tuple[int, int]] = {
    2: (settings.GUILD_L2_COPPER_COST, settings.GUILD_L2_NXC_COST),
    3: (settings.GUILD_L3_COPPER_COST, settings.GUILD_L3_NXC_COST),
    4: (settings.GUILD_L4_COPPER_COST, settings.GUILD_L4_NXC_COST),
}


def _coerce_now(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(UTC)
    if now.tzinfo is None:
        return now.replace(tzinfo=UTC)
    return now


def calculate_maintenance(member_count: int) -> int:
    """Calculate daily guild maintenance in copper."""
    return int(
        round(
            GUILD_BASE_MAINTENANCE_COPPER
            + max(0, member_count) ** GUILD_MEMBER_POWER * GUILD_MEMBER_FACTOR
        )
    )


async def _require_agent(session: AsyncSession, agent_id: int) -> Agent:
    result = await session.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if agent is None:
        raise ValueError(f"Agent {agent_id} not found")
    return agent


async def _require_region(session: AsyncSession, region_id: int) -> Region:
    result = await session.execute(select(Region).where(Region.id == region_id))
    region = result.scalar_one_or_none()
    if region is None:
        raise ValueError(f"Region {region_id} not found")
    return region


async def _get_active_membership(
    session: AsyncSession,
    *,
    agent_id: int,
) -> GuildMember | None:
    result = await session.execute(
        select(GuildMember)
        .join(Guild, Guild.id == GuildMember.guild_id)
        .where(
            GuildMember.agent_id == agent_id,
            Guild.is_active.is_(True),
        )
    )
    return result.scalar_one_or_none()


async def _require_membership(
    session: AsyncSession,
    *,
    agent_id: int,
    guild_id: int,
) -> GuildMember:
    result = await session.execute(
        select(GuildMember)
        .where(
            GuildMember.agent_id == agent_id,
            GuildMember.guild_id == guild_id,
        )
        .with_for_update()
    )
    membership = result.scalar_one_or_none()
    if membership is None:
        raise ValueError(f"Agent {agent_id} is not a member of guild {guild_id}")
    return membership


async def _require_guild_for_update(session: AsyncSession, guild_id: int) -> Guild:
    result = await session.execute(
        select(Guild).where(Guild.id == guild_id).with_for_update()
    )
    guild = result.scalar_one_or_none()
    if guild is None:
        raise ValueError(f"Guild {guild_id} not found")
    return guild


async def _count_members(session: AsyncSession, guild_id: int) -> int:
    result = await session.execute(
        select(func.count())
        .select_from(GuildMember)
        .where(GuildMember.guild_id == guild_id)
    )
    return int(result.scalar() or 0)


async def _serialize_guild(session: AsyncSession, guild_id: int) -> dict:
    guild = await session.get(Guild, guild_id)
    if guild is None:
        raise ValueError(f"Guild {guild_id} not found")

    result = await session.execute(
        select(GuildMember, Agent.name)
        .join(Agent, Agent.id == GuildMember.agent_id)
        .where(GuildMember.guild_id == guild_id)
        .order_by(Agent.name)
    )
    rank_order = {
        GuildRank.LEADER: 0,
        GuildRank.OFFICER: 1,
        GuildRank.MEMBER: 2,
        GuildRank.RECRUIT: 3,
    }
    members = sorted(
        result.all(),
        key=lambda row: (rank_order.get(row[0].rank, 99), row[1]),
    )
    return {
        "guild_id": guild.id,
        "name": guild.name,
        "level": guild.level,
        "treasury": int(guild.treasury),
        "home_region_id": guild.home_region_id,
        "is_active": bool(guild.is_active),
        "member_count": len(members),
        "members": [
            {
                "agent_id": member.agent_id,
                "rank": member.rank.value,
                "share_percentage": float(member.share_percentage),
                "joined_at": member.joined_at.isoformat() if member.joined_at else None,
                "name": agent_name,
            }
            for member, agent_name in members
        ],
    }


async def list_guilds(
    session: AsyncSession,
    *,
    region_id: int | None = None,
    active_only: bool = True,
) -> list[dict]:
    query = select(Guild).order_by(Guild.level.desc(), Guild.name)
    if active_only:
        query = query.where(Guild.is_active.is_(True))
    if region_id is not None:
        query = query.where(Guild.home_region_id == region_id)

    result = await session.execute(query)
    guilds = result.scalars().all()
    return [await _serialize_guild(session, guild.id) for guild in guilds]


async def create_guild(
    session: AsyncSession, agent_id: int, name: str, home_region_id: int
) -> dict:
    """Create a new guild. Agent becomes leader.

    Returns: {"guild_id", "name", "home_region_id"}
    """
    await _require_agent(session, agent_id)
    await _require_region(session, home_region_id)

    existing_name = await session.execute(select(Guild).where(Guild.name == name))
    if existing_name.scalar_one_or_none() is not None:
        raise ValueError(f"Guild name '{name}' is already taken")

    membership = await _get_active_membership(session, agent_id=agent_id)
    if membership is not None:
        raise ValueError(f"Agent {agent_id} is already in an active guild")

    guild = Guild(
        name=name,
        level=1,
        treasury=0,
        home_region_id=home_region_id,
        maintenance_cost_per_day=calculate_maintenance(1),
        is_active=True,
    )
    session.add(guild)
    await session.flush()

    session.add(
        GuildMember(
            guild_id=guild.id,
            agent_id=agent_id,
            rank=GuildRank.LEADER,
            share_percentage=0.0,
        )
    )
    await session.flush()

    await log_diplomacy_decision(
        session,
        agent_id,
        action="create_guild",
        detail=f"Created guild {name}",
    )
    return await _serialize_guild(session, guild.id)


async def join_guild(session: AsyncSession, agent_id: int, guild_id: int) -> dict:
    """Join a guild as recruit."""
    await _require_agent(session, agent_id)
    guild = await _require_guild_for_update(session, guild_id)
    if not guild.is_active:
        raise ValueError(f"Guild {guild_id} is inactive")

    membership = await _get_active_membership(session, agent_id=agent_id)
    if membership is not None:
        if membership.guild_id == guild_id:
            raise ValueError(f"Agent {agent_id} is already in guild {guild_id}")
        raise ValueError(f"Agent {agent_id} is already in another active guild")

    member_count = await _count_members(session, guild_id)
    max_members = max(1, guild.level * GUILD_MAX_MEMBERS_PER_LEVEL)
    if member_count >= max_members:
        raise ValueError(
            f"Guild {guild_id} is full ({member_count}/{max_members})"
        )

    session.add(
        GuildMember(
            guild_id=guild_id,
            agent_id=agent_id,
            rank=GuildRank.RECRUIT,
            share_percentage=0.0,
        )
    )
    guild.maintenance_cost_per_day = calculate_maintenance(member_count + 1)
    await session.flush()

    await log_diplomacy_decision(
        session,
        agent_id,
        action="join_guild",
        detail=f"Joined guild #{guild_id}",
    )
    return {"guild_id": guild_id, "rank": GuildRank.RECRUIT.value}


async def leave_guild(session: AsyncSession, agent_id: int, guild_id: int) -> bool:
    """Leave a guild."""
    guild = await _require_guild_for_update(session, guild_id)
    membership = await _require_membership(session, agent_id=agent_id, guild_id=guild_id)
    if membership.rank == GuildRank.LEADER:
        raise ValueError("Guild leader cannot leave without disbanding the guild")

    await session.delete(membership)
    remaining_members = max(0, await _count_members(session, guild_id) - 1)
    guild.maintenance_cost_per_day = calculate_maintenance(remaining_members)
    await session.flush()
    return True


async def disband_guild(
    session: AsyncSession,
    leader_agent_id: int,
    guild_id: int,
) -> bool:
    guild = await _require_guild_for_update(session, guild_id)
    membership = await _require_membership(
        session,
        agent_id=leader_agent_id,
        guild_id=guild_id,
    )
    if membership.rank != GuildRank.LEADER:
        raise ValueError(f"Agent {leader_agent_id} is not the leader of guild {guild_id}")

    leader = await session.get(Agent, leader_agent_id)
    if leader is None:
        raise ValueError(f"Agent {leader_agent_id} not found")

    leader.personal_balance = int(leader.personal_balance) + int(guild.treasury)
    guild.treasury = 0
    guild.is_active = False

    await session.execute(delete(GuildMember).where(GuildMember.guild_id == guild_id))
    await session.flush()
    return True


async def promote_member(
    session: AsyncSession, leader_agent_id: int, target_agent_id: int, guild_id: int, new_rank: str
) -> dict:
    """Promote a guild member."""
    guild = await _require_guild_for_update(session, guild_id)
    if not guild.is_active:
        raise ValueError(f"Guild {guild_id} is inactive")

    actor_membership = await _require_membership(
        session,
        agent_id=leader_agent_id,
        guild_id=guild_id,
    )
    if actor_membership.rank not in {GuildRank.LEADER, GuildRank.OFFICER}:
        raise ValueError("Only guild leaders or officers can promote members")

    target_membership = await _require_membership(
        session,
        agent_id=target_agent_id,
        guild_id=guild_id,
    )
    target_rank = GuildRank(new_rank)

    if target_rank == GuildRank.LEADER:
        raise ValueError("Leadership transfer is not implemented")
    if actor_membership.rank == GuildRank.OFFICER and target_rank == GuildRank.OFFICER:
        raise ValueError("Only the guild leader can promote another officer")
    if target_membership.rank == GuildRank.LEADER:
        raise ValueError("Guild leader rank cannot be modified here")

    target_membership.rank = target_rank
    await session.flush()
    return {"agent_id": target_agent_id, "new_rank": target_rank.value}


async def deposit_to_treasury(
    session: AsyncSession, agent_id: int, guild_id: int, amount: int
) -> int:
    """Deposit copper to guild treasury. Returns new treasury balance."""
    if amount <= 0:
        raise ValueError("amount must be greater than 0")

    guild = await _require_guild_for_update(session, guild_id)
    if not guild.is_active:
        raise ValueError(f"Guild {guild_id} is inactive")

    await _require_membership(session, agent_id=agent_id, guild_id=guild_id)

    result = await session.execute(
        select(Agent).where(Agent.id == agent_id).with_for_update()
    )
    agent = result.scalar_one_or_none()
    if agent is None:
        raise ValueError(f"Agent {agent_id} not found")

    if int(agent.personal_balance) < amount:
        raise ValueError(
            f"Agent {agent_id} has insufficient balance for deposit {amount}"
        )

    agent.personal_balance = int(agent.personal_balance) - amount
    guild.treasury = int(guild.treasury) + amount
    await session.flush()
    return int(guild.treasury)


async def check_guild_maintenance(session: AsyncSession) -> list[int]:
    """Check and deduct guild maintenance. Returns disbanded guild IDs."""
    summary = await collect_maintenance(session)
    return summary["disbanded_guild_ids"]


async def collect_maintenance(
    session: AsyncSession,
    now: datetime | None = None,
) -> dict:
    now = _coerce_now(now)

    result = await session.execute(
        select(Guild).where(Guild.is_active.is_(True)).with_for_update()
    )
    guilds = result.scalars().all()

    disbanded_guild_ids: list[int] = []
    charged = 0
    for guild in guilds:
        member_count = await _count_members(session, guild.id)
        maintenance = calculate_maintenance(member_count)
        guild.maintenance_cost_per_day = maintenance

        if int(guild.treasury) >= maintenance:
            guild.treasury = int(guild.treasury) - maintenance
            charged += 1
            continue

        guild.treasury = 0
        guild.is_active = False
        disbanded_guild_ids.append(guild.id)
        await session.execute(delete(GuildMember).where(GuildMember.guild_id == guild.id))

    await session.flush()
    return {
        "guilds_charged": charged,
        "guilds_disbanded": len(disbanded_guild_ids),
        "disbanded_guild_ids": disbanded_guild_ids,
        "processed_at": now.isoformat(),
    }


async def get_guild_info(session: AsyncSession, guild_id: int) -> dict:
    """Get guild info with member list."""
    return await _serialize_guild(session, guild_id)


async def upgrade_guild(
    session: AsyncSession,
    agent_id: int,
    guild_id: int,
) -> dict:
    """Upgrade a guild to the next level. Costs copper + NXC from guild treasury.

    Returns: {"guild_id", "old_level", "new_level", "copper_cost", "nxc_cost"}
    Raises: ValueError if not leader, max level, or insufficient funds
    """
    from agentropolis.models.guild import GuildMember, GuildRank

    # Get guild with lock
    result = await session.execute(
        select(Guild).where(Guild.id == guild_id).with_for_update()
    )
    guild = result.scalar_one_or_none()
    if guild is None:
        raise ValueError(f"Guild {guild_id} not found")

    if not guild.is_active:
        raise ValueError(f"Guild {guild_id} is not active")

    # Check agent is leader
    result = await session.execute(
        select(GuildMember).where(
            GuildMember.guild_id == guild_id,
            GuildMember.agent_id == agent_id,
            GuildMember.rank == GuildRank.LEADER,
        )
    )
    if result.scalar_one_or_none() is None:
        raise ValueError(f"Agent {agent_id} is not the leader of guild {guild_id}")

    next_level = guild.level + 1
    costs = GUILD_UPGRADE_COSTS.get(next_level)
    if costs is None:
        raise ValueError(f"Guild is already at max level ({guild.level})")

    copper_cost, nxc_cost = costs

    # Check guild treasury
    if guild.treasury < copper_cost:
        raise ValueError(
            f"Insufficient guild treasury: need {copper_cost} copper, have {guild.treasury}"
        )

    # Deduct costs
    guild.treasury -= copper_cost
    # NXC cost would need inventory deduction - tracked but simplified
    old_level = guild.level
    guild.level = next_level

    await session.flush()

    return {
        "guild_id": guild_id,
        "old_level": old_level,
        "new_level": next_level,
        "copper_cost": copper_cost,
        "nxc_cost": nxc_cost,
    }


def get_guild_level_benefits(level: int) -> dict:
    """Get benefits description for a guild level."""
    benefits = {1: {"description": "Basic guild"}}
    if level >= 2:
        benefits[2] = {"description": "Guild warehouse unlocked"}
    if level >= 3:
        benefits[3] = {"description": "Member tax reduction (-5%)"}
    if level >= 4:
        benefits[4] = {"description": "Guild shop discount (-10%)"}
    return benefits


async def get_agent_guild_snapshot(
    session: AsyncSession,
    agent_id: int,
) -> dict | None:
    result = await session.execute(
        select(Guild, GuildMember)
        .join(GuildMember, GuildMember.guild_id == Guild.id)
        .where(
            GuildMember.agent_id == agent_id,
            Guild.is_active.is_(True),
        )
    )
    row = result.first()
    if row is None:
        return None
    guild, membership = row
    return {
        "guild_id": guild.id,
        "level": int(guild.level),
        "rank": membership.rank.value,
        "home_region_id": guild.home_region_id,
        "benefits": get_guild_level_benefits(int(guild.level)),
    }


def get_guild_tax_reduction(level: int) -> float:
    return 0.05 if int(level) >= 3 else 0.0


def get_guild_shop_discount(level: int) -> float:
    return 0.10 if int(level) >= 4 else 0.0


async def get_agent_guild_effects(
    session: AsyncSession,
    agent_id: int,
) -> dict[str, float | int | None]:
    snapshot = await get_agent_guild_snapshot(session, agent_id)
    if snapshot is None:
        return {
            "guild_id": None,
            "level": 0,
            "tax_reduction": 0.0,
            "npc_discount": 0.0,
        }
    level = int(snapshot["level"])
    return {
        "guild_id": snapshot["guild_id"],
        "level": level,
        "home_region_id": snapshot["home_region_id"],
        "tax_reduction": get_guild_tax_reduction(level),
        "npc_discount": get_guild_shop_discount(level),
        "warehouse_bonus": 500 if level >= 2 else 0,
    }
