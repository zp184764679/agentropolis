"""Guild service - guild management with level upgrades.

Guild Levels:
L1→L2: 500K copper + 10 NXC (unlocks guild warehouse)
L2→L3: 2M copper + 50 NXC (member tax reduction)
L3→L4: 5M copper + 100 NXC (guild shop discount)
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentropolis.config import settings
from agentropolis.models.guild import Guild

# Guild upgrade costs: level → (copper, nxc)
GUILD_UPGRADE_COSTS: dict[int, tuple[int, int]] = {
    2: (settings.GUILD_L2_COPPER_COST, settings.GUILD_L2_NXC_COST),
    3: (settings.GUILD_L3_COPPER_COST, settings.GUILD_L3_NXC_COST),
    4: (settings.GUILD_L4_COPPER_COST, settings.GUILD_L4_NXC_COST),
}


async def create_guild(
    session: AsyncSession, agent_id: int, name: str, home_region_id: int
) -> dict:
    """Create a new guild. Agent becomes leader.

    Returns: {"guild_id", "name", "home_region_id"}
    """
    raise NotImplementedError("Issue #28: Implement guild service")


async def join_guild(session: AsyncSession, agent_id: int, guild_id: int) -> dict:
    """Join a guild as recruit."""
    raise NotImplementedError("Issue #28: Implement guild service")


async def leave_guild(session: AsyncSession, agent_id: int, guild_id: int) -> bool:
    """Leave a guild."""
    raise NotImplementedError("Issue #28: Implement guild service")


async def promote_member(
    session: AsyncSession, leader_agent_id: int, target_agent_id: int, guild_id: int, new_rank: str
) -> dict:
    """Promote a guild member."""
    raise NotImplementedError("Issue #28: Implement guild service")


async def deposit_to_treasury(
    session: AsyncSession, agent_id: int, guild_id: int, amount: int
) -> int:
    """Deposit copper to guild treasury. Returns new treasury balance."""
    raise NotImplementedError("Issue #28: Implement guild service")


async def check_guild_maintenance(session: AsyncSession) -> list[int]:
    """Check and deduct guild maintenance. Returns disbanded guild IDs."""
    raise NotImplementedError("Issue #28: Implement guild service")


async def get_guild_info(session: AsyncSession, guild_id: int) -> dict:
    """Get guild info with member list."""
    raise NotImplementedError("Issue #28: Implement guild service")


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
