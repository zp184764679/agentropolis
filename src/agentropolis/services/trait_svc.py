"""Agent Trait service - evaluate, award, and decay traits based on behavior.

Traits are the "boxing record" of an agent. They're earned through sustained
behavior patterns and provide small mechanical bonuses. All traits are publicly
visible, serving as both an honor system and an intelligence system.
"""

import logging
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agentropolis.models.agent_trait import AgentTrait, TraitId, TraitTier
from agentropolis.models.decision_log import AgentDecisionLog, DecisionType

logger = logging.getLogger(__name__)

# ─── Trait Definitions ─────────────────────────────────────────────────────

# trait_id → {thresholds per tier, bonus description}
TRAIT_DEFS: dict[TraitId, dict] = {
    TraitId.IRON_TRADER: {
        "thresholds": {TraitTier.BRONZE: 100, TraitTier.SILVER: 200, TraitTier.GOLD: 500},
        "counter": "profitable_trades",
        "bonus": "trade_tax_reduction",
        "values": {TraitTier.BRONZE: 0.05, TraitTier.SILVER: 0.075, TraitTier.GOLD: 0.10},
    },
    TraitId.WARMONGER: {
        "thresholds": {TraitTier.BRONZE: 20, TraitTier.SILVER: 40, TraitTier.GOLD: 100},
        "counter": "successful_attacks",
        "bonus": "attack_bonus",
        "values": {TraitTier.BRONZE: 0.10, TraitTier.SILVER: 0.15, TraitTier.GOLD: 0.20},
    },
    TraitId.IRON_WALL: {
        "thresholds": {TraitTier.BRONZE: 15, TraitTier.SILVER: 30, TraitTier.GOLD: 75},
        "counter": "successful_defenses",
        "bonus": "defense_bonus",
        "values": {TraitTier.BRONZE: 0.15, TraitTier.SILVER: 0.20, TraitTier.GOLD: 0.30},
    },
    TraitId.SUPPLY_MASTER: {
        "thresholds": {TraitTier.BRONZE: 5, TraitTier.SILVER: 10, TraitTier.GOLD: 25},
        "counter": "profitable_buildings",
        "bonus": "production_speed",
        "values": {TraitTier.BRONZE: 0.10, TraitTier.SILVER: 0.15, TraitTier.GOLD: 0.20},
    },
    TraitId.BACKSTABBER: {
        "thresholds": {TraitTier.BRONZE: 5, TraitTier.SILVER: 10, TraitTier.GOLD: 25},
        "counter": "broken_treaties",
        "bonus": "raid_loot_bonus",
        "values": {TraitTier.BRONZE: 0.20, TraitTier.SILVER: 0.30, TraitTier.GOLD: 0.40},
    },
    TraitId.NXC_TYCOON: {
        "thresholds": {TraitTier.BRONZE: 1000, TraitTier.SILVER: 5000, TraitTier.GOLD: 25000},
        "counter": "nxc_held",
        "bonus": "mining_output",
        "values": {TraitTier.BRONZE: 0.05, TraitTier.SILVER: 0.08, TraitTier.GOLD: 0.12},
    },
    TraitId.PHOENIX: {
        "thresholds": {TraitTier.BRONZE: 10, TraitTier.SILVER: 20, TraitTier.GOLD: 50},
        "counter": "respawns",
        "bonus": "respawn_balance_keep",
        "values": {TraitTier.BRONZE: 0.25, TraitTier.SILVER: 0.35, TraitTier.GOLD: 0.50},
    },
    TraitId.ROAD_WARRIOR: {
        "thresholds": {TraitTier.BRONZE: 50, TraitTier.SILVER: 100, TraitTier.GOLD: 250},
        "counter": "region_travels",
        "bonus": "travel_time_reduction",
        "values": {TraitTier.BRONZE: 0.10, TraitTier.SILVER: 0.15, TraitTier.GOLD: 0.20},
    },
    TraitId.GUILD_LEADER: {
        "thresholds": {TraitTier.BRONZE: 1, TraitTier.SILVER: 1, TraitTier.GOLD: 1},
        "counter": "guild_members_led",
        "bonus": "guild_xp_bonus",
        "values": {TraitTier.BRONZE: 0.10, TraitTier.SILVER: 0.15, TraitTier.GOLD: 0.20},
    },
    TraitId.MERCHANT_PRINCE: {
        "thresholds": {TraitTier.BRONZE: 1_000_000, TraitTier.SILVER: 5_000_000, TraitTier.GOLD: 25_000_000},
        "counter": "total_trade_volume",
        "bonus": "npc_price_discount",
        "values": {TraitTier.BRONZE: 0.05, TraitTier.SILVER: 0.08, TraitTier.GOLD: 0.12},
    },
}

# How fast traits decay without activity (days of inactivity before tier drops)
DECAY_DAYS = 7
TIER_MULTIPLIERS = {TraitTier.BRONZE: 1.0, TraitTier.SILVER: 1.5, TraitTier.GOLD: 2.0}


# ─── Query ─────────────────────────────────────────────────────────────────


async def get_agent_traits(session: AsyncSession, agent_id: int) -> list[dict]:
    """Get all traits for an agent."""
    result = await session.execute(
        select(AgentTrait).where(AgentTrait.agent_id == agent_id)
    )
    return [_trait_to_dict(t) for t in result.scalars().all()]


async def get_trait_bonus(
    session: AsyncSession, agent_id: int, bonus_type: str
) -> float:
    """Get the total bonus for a specific bonus type from all traits.

    Returns the bonus as a fraction (e.g., 0.10 for +10%).
    """
    result = await session.execute(
        select(AgentTrait).where(AgentTrait.agent_id == agent_id)
    )
    traits = result.scalars().all()

    total_bonus = 0.0
    for trait in traits:
        defn = TRAIT_DEFS.get(trait.trait_id)
        if defn and defn["bonus"] == bonus_type:
            total_bonus += defn["values"][trait.tier]

    return total_bonus


# ─── Evaluate & Award ──────────────────────────────────────────────────────


async def evaluate_agent_traits(
    session: AsyncSession,
    agent_id: int,
    now: datetime | None = None,
) -> dict:
    """Evaluate an agent's behavior and award/upgrade/decay traits.

    Called during housekeeping. Returns summary of changes.
    """
    if now is None:
        now = datetime.now(UTC)

    counters = await _count_agent_achievements(session, agent_id)

    # Get existing traits
    result = await session.execute(
        select(AgentTrait).where(AgentTrait.agent_id == agent_id)
    )
    existing = {t.trait_id: t for t in result.scalars().all()}

    awarded = []
    upgraded = []
    decayed = []

    for trait_id, defn in TRAIT_DEFS.items():
        counter_name = defn["counter"]
        count = counters.get(counter_name, 0)
        thresholds = defn["thresholds"]

        # Determine which tier the agent qualifies for
        qualified_tier = None
        for tier in [TraitTier.GOLD, TraitTier.SILVER, TraitTier.BRONZE]:
            if count >= thresholds[tier]:
                qualified_tier = tier
                break

        if trait_id in existing:
            trait = existing[trait_id]
            if qualified_tier is None:
                # Decay check: if inactive for too long, remove trait
                days_inactive = (now - trait.last_progress_at).total_seconds() / 86400
                if days_inactive > DECAY_DAYS:
                    if trait.tier == TraitTier.BRONZE:
                        await session.delete(trait)
                        decayed.append(trait_id.value)
                    else:
                        # Downgrade tier
                        new_tier = TraitTier(trait.tier.value - 1)
                        trait.tier = new_tier
                        trait.bonus_multiplier = TIER_MULTIPLIERS[new_tier]
                        trait.last_progress_at = now
                        decayed.append(f"{trait_id.value} → {new_tier.name}")
            elif qualified_tier.value > trait.tier.value:
                # Upgrade
                trait.tier = qualified_tier
                trait.bonus_multiplier = TIER_MULTIPLIERS[qualified_tier]
                trait.progress = count
                trait.last_progress_at = now
                upgraded.append(f"{trait_id.value} → {qualified_tier.name}")
            else:
                # Maintain: update progress
                trait.progress = count
                trait.last_progress_at = now
        elif qualified_tier is not None:
            # Award new trait
            new_trait = AgentTrait(
                agent_id=agent_id,
                trait_id=trait_id,
                tier=qualified_tier,
                progress=count,
                bonus_multiplier=TIER_MULTIPLIERS[qualified_tier],
                earned_at=now,
                last_progress_at=now,
            )
            session.add(new_trait)
            awarded.append(f"{trait_id.value} ({qualified_tier.name})")

    return {
        "agent_id": agent_id,
        "awarded": awarded,
        "upgraded": upgraded,
        "decayed": decayed,
    }


async def _count_agent_achievements(
    session: AsyncSession, agent_id: int
) -> dict[str, int]:
    """Count various achievement metrics for an agent from decision logs."""
    counters: dict[str, int] = {}

    # Count profitable trades from decision log
    result = await session.execute(
        select(func.count()).where(
            AgentDecisionLog.agent_id == agent_id,
            AgentDecisionLog.decision_type == DecisionType.TRADE,
            AgentDecisionLog.is_profitable == True,  # noqa: E712
        )
    )
    counters["profitable_trades"] = result.scalar() or 0

    # Count successful attacks
    result = await session.execute(
        select(func.count()).where(
            AgentDecisionLog.agent_id == agent_id,
            AgentDecisionLog.decision_type == DecisionType.COMBAT,
            AgentDecisionLog.is_profitable == True,  # noqa: E712
            AgentDecisionLog.context_snapshot["role"].as_string() == "attacker",
        )
    )
    counters["successful_attacks"] = result.scalar() or 0

    # Count successful defenses
    result = await session.execute(
        select(func.count()).where(
            AgentDecisionLog.agent_id == agent_id,
            AgentDecisionLog.decision_type == DecisionType.COMBAT,
            AgentDecisionLog.is_profitable == True,  # noqa: E712
            AgentDecisionLog.context_snapshot["role"].as_string() == "defender",
        )
    )
    counters["successful_defenses"] = result.scalar() or 0

    # Total trade volume (sum of amount_copper for trade decisions)
    result = await session.execute(
        select(func.coalesce(func.sum(AgentDecisionLog.amount_copper), 0)).where(
            AgentDecisionLog.agent_id == agent_id,
            AgentDecisionLog.decision_type == DecisionType.TRADE,
        )
    )
    counters["total_trade_volume"] = result.scalar() or 0

    # Count travels
    result = await session.execute(
        select(func.count()).where(
            AgentDecisionLog.agent_id == agent_id,
            AgentDecisionLog.decision_type == DecisionType.TRAVEL,
        )
    )
    counters["region_travels"] = result.scalar() or 0

    # Count respawns (from context snapshot)
    result = await session.execute(
        select(func.count()).where(
            AgentDecisionLog.agent_id == agent_id,
            AgentDecisionLog.summary.like("%respawn%"),
        )
    )
    counters["respawns"] = result.scalar() or 0

    # Broken treaties
    result = await session.execute(
        select(func.count()).where(
            AgentDecisionLog.agent_id == agent_id,
            AgentDecisionLog.decision_type == DecisionType.DIPLOMACY,
            AgentDecisionLog.summary.like("%broke%treaty%"),
        )
    )
    counters["broken_treaties"] = result.scalar() or 0

    # ── Live data counters (not from decision logs) ──

    # NXC held: query agent's NXC inventory across all regions
    try:
        from agentropolis.models.inventory import Inventory
        from agentropolis.models.resource import Resource

        nxc_result = await session.execute(
            select(func.coalesce(func.sum(Inventory.quantity), 0))
            .join(Resource, Inventory.resource_id == Resource.id)
            .where(
                Inventory.agent_id == agent_id,
                Resource.ticker == "NXC",
            )
        )
        counters["nxc_held"] = nxc_result.scalar() or 0
    except Exception:
        counters["nxc_held"] = 0

    # Profitable buildings: count PRODUCING buildings owned by agent's companies
    try:
        from agentropolis.models.building import Building, BuildingStatus
        from agentropolis.models.company import Company

        bld_result = await session.execute(
            select(func.count())
            .select_from(Building)
            .join(Company, Building.company_id == Company.id)
            .where(
                Company.founder_agent_id == agent_id,
                Building.status == BuildingStatus.PRODUCING,
            )
        )
        counters["profitable_buildings"] = bld_result.scalar() or 0
    except Exception:
        counters["profitable_buildings"] = 0

    # Guild members led: count members if agent is a guild leader
    try:
        from agentropolis.models.guild import GuildMember, GuildRank

        leader_result = await session.execute(
            select(GuildMember.guild_id).where(
                GuildMember.agent_id == agent_id,
                GuildMember.rank == GuildRank.LEADER,
            )
        )
        leader_guilds = leader_result.scalars().all()
        if leader_guilds:
            member_count_result = await session.execute(
                select(func.count()).where(
                    GuildMember.guild_id.in_(leader_guilds),
                )
            )
            counters["guild_members_led"] = member_count_result.scalar() or 0
        else:
            counters["guild_members_led"] = 0
    except Exception:
        counters["guild_members_led"] = 0

    return counters


# ─── Bonus Application Helpers ─────────────────────────────────────────────


async def get_combat_trait_modifiers(
    session: AsyncSession, agent_id: int
) -> dict[str, float]:
    """Get combat-related trait bonuses for an agent.

    Returns {"attack_bonus": float, "defense_bonus": float}
    """
    attack = await get_trait_bonus(session, agent_id, "attack_bonus")
    defense = await get_trait_bonus(session, agent_id, "defense_bonus")
    return {"attack_bonus": attack, "defense_bonus": defense}


async def get_trade_trait_modifiers(
    session: AsyncSession, agent_id: int
) -> dict[str, float]:
    """Get trade-related trait bonuses."""
    tax_reduction = await get_trait_bonus(session, agent_id, "trade_tax_reduction")
    npc_discount = await get_trait_bonus(session, agent_id, "npc_price_discount")
    raid_loot = await get_trait_bonus(session, agent_id, "raid_loot_bonus")
    return {
        "trade_tax_reduction": tax_reduction,
        "npc_price_discount": npc_discount,
        "raid_loot_bonus": raid_loot,
    }


async def get_production_trait_bonus(
    session: AsyncSession, agent_id: int
) -> float:
    """Get production speed bonus from traits."""
    return await get_trait_bonus(session, agent_id, "production_speed")


async def get_mining_trait_bonus(
    session: AsyncSession, agent_id: int
) -> float:
    """Get mining output bonus from NXC_TYCOON trait."""
    return await get_trait_bonus(session, agent_id, "mining_output")


# ─── Helpers ───────────────────────────────────────────────────────────────


def _trait_to_dict(trait: AgentTrait) -> dict:
    defn = TRAIT_DEFS.get(trait.trait_id, {})
    return {
        "trait_id": trait.trait_id.value,
        "tier": trait.tier.name,
        "progress": trait.progress,
        "bonus_type": defn.get("bonus", "unknown"),
        "bonus_value": defn.get("values", {}).get(trait.tier, 0.0),
        "earned_at": trait.earned_at.isoformat(),
        "last_progress_at": trait.last_progress_at.isoformat(),
    }
