"""Strategy Profile service - CRUD and doctrine-based modifier calculations.

The strategy profile determines real mechanical differences between agents:
- Combat doctrine → attack/defense multipliers
- Risk tolerance → trade profit/damage modifiers
- Primary focus → XP gain rate bonuses
- Diplomatic stance → initial trust values

`StrategyProfile.standing_orders` is now treated as a public compatibility
mirror. Canonical standing-order writes live in `AutonomyState`.
"""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentropolis.models.strategy_profile import (
    CombatDoctrine,
    DiplomaticStance,
    PrimaryFocus,
    StrategyProfile,
)

logger = logging.getLogger(__name__)

# ─── Doctrine Modifiers ────────────────────────────────────────────────────

DOCTRINE_MODIFIERS: dict[CombatDoctrine, dict[str, float]] = {
    CombatDoctrine.OFFENSIVE: {"attack": 1.20, "defense": 0.85, "commerce_xp": 1.0},
    CombatDoctrine.BALANCED: {"attack": 1.00, "defense": 1.00, "commerce_xp": 1.0},
    CombatDoctrine.DEFENSIVE: {"attack": 0.90, "defense": 1.25, "commerce_xp": 1.0},
    CombatDoctrine.PACIFIST: {"attack": 0.50, "defense": 0.50, "commerce_xp": 1.10},
}

STANCE_TRUST: dict[DiplomaticStance, float] = {
    DiplomaticStance.OPEN: 10.0,
    DiplomaticStance.CAUTIOUS: 0.0,
    DiplomaticStance.HOSTILE: -15.0,
    DiplomaticStance.ISOLATIONIST: -5.0,
}

# Focus → which skill categories get the bonus
FOCUS_SKILLS: dict[PrimaryFocus, list[str]] = {
    PrimaryFocus.COMBAT: ["Melee", "Tactics", "Fortification"],
    PrimaryFocus.CRAFTING: ["Smithing", "Engineering", "Alchemy"],
    PrimaryFocus.COMMERCE: ["Trading", "Logistics", "Negotiation"],
    PrimaryFocus.GATHERING: ["Mining", "Woodcutting", "Farming"],
    PrimaryFocus.LEADERSHIP: ["Command", "Diplomacy", "Management"],
}


# ─── CRUD ──────────────────────────────────────────────────────────────────


async def get_profile(session: AsyncSession, agent_id: int) -> StrategyProfile | None:
    """Get an agent's strategy profile."""
    result = await session.execute(
        select(StrategyProfile).where(StrategyProfile.agent_id == agent_id)
    )
    return result.scalar_one_or_none()


async def create_or_update_profile(
    session: AsyncSession,
    agent_id: int,
    *,
    combat_doctrine: str | None = None,
    risk_tolerance: float | None = None,
    primary_focus: str | None = None,
    secondary_focus: str | None = None,
    default_stance: str | None = None,
    standing_orders: dict | None = None,
) -> dict:
    """Create or update an agent's strategy profile.

    `standing_orders` is retained only as a compatibility bridge for older
    internal callers. Canonical standing-order writes should go through
    `services.autopilot.update_standing_orders()` / `/api/autonomy/standing-orders`.

    Returns the updated profile as a dict.
    """
    profile = await get_profile(session, agent_id)

    if profile is None:
        profile = StrategyProfile(agent_id=agent_id)
        session.add(profile)

    if combat_doctrine is not None:
        profile.combat_doctrine = CombatDoctrine(combat_doctrine)
    if risk_tolerance is not None:
        if not 0.0 <= risk_tolerance <= 1.0:
            raise ValueError("risk_tolerance must be between 0.0 and 1.0")
        profile.risk_tolerance = risk_tolerance
    if primary_focus is not None:
        profile.primary_focus = PrimaryFocus(primary_focus)
    if secondary_focus is not None:
        if secondary_focus == "":
            profile.secondary_focus = None
        else:
            sf = PrimaryFocus(secondary_focus)
            if sf == profile.primary_focus:
                raise ValueError("secondary_focus cannot be the same as primary_focus")
            profile.secondary_focus = sf
    if default_stance is not None:
        profile.default_stance = DiplomaticStance(default_stance)
    if standing_orders is not None:
        from agentropolis.services.autopilot import (
            _normalize_standing_orders,
            ensure_autonomy_state,
        )

        profile.standing_orders = standing_orders
        normalized = None
        if set(standing_orders).issubset({"buy_rules", "sell_rules"}):
            try:
                normalized = _normalize_standing_orders(standing_orders)
            except ValueError:
                normalized = None
        if normalized is not None:
            profile.standing_orders = normalized if any(normalized.values()) else None
            autonomy_state = await ensure_autonomy_state(session, agent_id)
            autonomy_state.standing_orders = normalized
    profile.version += 1
    await session.flush()

    return _profile_to_dict(profile)


async def get_public_profile(session: AsyncSession, agent_id: int) -> dict | None:
    """Get the public view of an agent's strategy (visible to other players).

    Includes doctrine, stance, and the public standing-order mirror — but NOT
    risk_tolerance.
    """
    profile = await get_profile(session, agent_id)
    if profile is None:
        return None

    return {
        "agent_id": agent_id,
        "combat_doctrine": profile.combat_doctrine.value,
        "primary_focus": profile.primary_focus.value,
        "secondary_focus": profile.secondary_focus.value if profile.secondary_focus else None,
        "default_stance": profile.default_stance.value,
        "standing_orders": profile.standing_orders,
        "version": profile.version,
    }


# ─── Modifier Calculations ─────────────────────────────────────────────────


def get_combat_modifiers(profile: StrategyProfile | None) -> dict[str, float]:
    """Get attack/defense multipliers from combat doctrine.

    Returns {"attack_mult": float, "defense_mult": float}
    """
    if profile is None:
        return {"attack_mult": 1.0, "defense_mult": 1.0}

    mods = DOCTRINE_MODIFIERS[profile.combat_doctrine]
    return {
        "attack_mult": mods["attack"],
        "defense_mult": mods["defense"],
    }


def get_risk_modifiers(profile: StrategyProfile | None) -> dict[str, float]:
    """Get risk-based modifiers.

    High risk (>0.7): +15% trade profit potential, +20% combat damage taken
    Low risk (<0.3): -10% NPC prices, -10% trade profit
    Mid: no modifier
    """
    if profile is None:
        return {"trade_profit_mult": 1.0, "damage_taken_mult": 1.0, "npc_price_mult": 1.0}

    rt = profile.risk_tolerance
    if rt > 0.7:
        return {
            "trade_profit_mult": 1.0 + (rt - 0.5) * 0.30,  # up to +15%
            "damage_taken_mult": 1.0 + (rt - 0.5) * 0.40,  # up to +20%
            "npc_price_mult": 1.0,
        }
    elif rt < 0.3:
        return {
            "trade_profit_mult": 1.0 - (0.5 - rt) * 0.20,  # up to -10%
            "damage_taken_mult": 1.0,
            "npc_price_mult": 1.0 - (0.5 - rt) * 0.20,  # up to -10% discount
        }
    else:
        return {"trade_profit_mult": 1.0, "damage_taken_mult": 1.0, "npc_price_mult": 1.0}


def get_xp_multiplier(profile: StrategyProfile | None, skill_category: str) -> float:
    """Get XP gain multiplier for a skill category based on focus settings.

    Primary focus: +50% XP (or +75% if no secondary)
    Secondary focus: +25% XP
    Non-focus: -25% XP
    """
    if profile is None:
        return 1.0

    primary_skills = FOCUS_SKILLS.get(profile.primary_focus, [])
    has_secondary = profile.secondary_focus is not None

    if skill_category in primary_skills:
        return 1.75 if not has_secondary else 1.50

    if has_secondary:
        secondary_skills = FOCUS_SKILLS.get(profile.secondary_focus, [])
        if skill_category in secondary_skills:
            return 1.25

    return 0.75


def get_initial_trust(profile: StrategyProfile | None) -> float:
    """Get initial trust value for new agent relationships."""
    if profile is None:
        return 0.0
    return STANCE_TRUST[profile.default_stance]


def get_stance_modifiers(profile: StrategyProfile | None) -> dict[str, float]:
    """Get stance-based modifiers for raids and NPC shops."""
    if profile is None:
        return {"raid_loot_mult": 1.0, "npc_discount": 0.0}

    if profile.default_stance == DiplomaticStance.HOSTILE:
        return {"raid_loot_mult": 1.05, "npc_discount": 0.0}
    elif profile.default_stance == DiplomaticStance.ISOLATIONIST:
        return {"raid_loot_mult": 1.0, "npc_discount": 0.05}
    else:
        return {"raid_loot_mult": 1.0, "npc_discount": 0.0}


# ─── Helpers ───────────────────────────────────────────────────────────────


def _profile_to_dict(profile: StrategyProfile) -> dict:
    return {
        "agent_id": profile.agent_id,
        "combat_doctrine": profile.combat_doctrine.value,
        "risk_tolerance": profile.risk_tolerance,
        "primary_focus": profile.primary_focus.value,
        "secondary_focus": profile.secondary_focus.value if profile.secondary_focus else None,
        "default_stance": profile.default_stance.value,
        "standing_orders": profile.standing_orders,
        "version": profile.version,
    }
