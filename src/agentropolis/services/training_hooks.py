"""Training hooks - integration layer for decision logging and strategy modifiers.

Other services call these helpers to:
1. Record decisions to the decision journal
2. Apply strategy profile XP multipliers
3. Apply strategy/trait modifiers to pricing and travel

This module prevents circular imports by lazy-importing the training services.
"""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from agentropolis.models.decision_log import DecisionType

logger = logging.getLogger(__name__)


# ─── Decision Recording Helpers ────────────────────────────────────────────


async def log_trade_decision(
    session: AsyncSession,
    agent_id: int,
    *,
    order_type: str,
    resource_ticker: str,
    quantity: int,
    price: int,
    region_id: int,
    resource_id: int | None = None,
    market_price: int | None = None,
    balance_before: int | None = None,
    order_id: int | None = None,
) -> None:
    """Log a trade decision (called from market_engine after order placement)."""
    from agentropolis.services.decision_log_svc import record_decision

    action = "买入" if order_type == "BUY" else "卖出"
    summary = f"{action} {quantity} {resource_ticker} @ {price}"

    await record_decision(
        session,
        agent_id,
        DecisionType.TRADE,
        summary,
        context_snapshot={
            "order_type": order_type,
            "resource_ticker": resource_ticker,
            "resource_id": resource_id,
            "quantity": quantity,
            "price": price,
            "market_price": market_price,
            "balance_before": balance_before,
        },
        reference_type="order",
        reference_id=order_id,
        region_id=region_id,
        amount_copper=price * quantity,
    )


async def log_combat_decision(
    session: AsyncSession,
    agent_id: int,
    *,
    role: str,
    contract_id: int,
    mission_type: str,
    region_id: int,
    reward: int = 0,
    enemy_count: int = 0,
    ally_count: int = 0,
    result: str | None = None,
    damage_dealt: float = 0.0,
    damage_taken: float = 0.0,
) -> None:
    """Log a combat decision (called from warfare_svc after execution)."""
    from agentropolis.services.decision_log_svc import record_decision

    role_cn = "进攻" if role == "attacker" else "防守"
    summary = f"{role_cn} 任务 {mission_type} (合同#{contract_id})"

    await record_decision(
        session,
        agent_id,
        DecisionType.COMBAT,
        summary,
        context_snapshot={
            "role": role,
            "contract_id": contract_id,
            "mission_type": mission_type,
            "reward": reward,
            "enemy_count": enemy_count,
            "ally_count": ally_count,
            "result": result,
            "damage_dealt": damage_dealt,
            "damage_taken": damage_taken,
            "loss": int(damage_taken * 100) if result == "defeat" else 0,
        },
        reference_type="contract",
        reference_id=contract_id,
        region_id=region_id,
        amount_copper=reward,
    )


async def log_production_decision(
    session: AsyncSession,
    agent_id: int,
    *,
    building_id: int,
    recipe_name: str,
    input_cost: int,
    output_value: int,
    region_id: int,
) -> None:
    """Log a production decision (called from production service)."""
    from agentropolis.services.decision_log_svc import record_decision

    summary = f"生产 {recipe_name} (建筑#{building_id})"

    await record_decision(
        session,
        agent_id,
        DecisionType.PRODUCTION,
        summary,
        context_snapshot={
            "building_id": building_id,
            "recipe_name": recipe_name,
            "input_cost": input_cost,
            "output_value": output_value,
        },
        reference_type="building",
        reference_id=building_id,
        region_id=region_id,
        amount_copper=input_cost,
    )


async def log_travel_decision(
    session: AsyncSession,
    agent_id: int,
    *,
    from_region_id: int,
    to_region_id: int,
    travel_time_seconds: int,
) -> None:
    """Log a travel decision (called from world_svc)."""
    from agentropolis.services.decision_log_svc import record_decision

    summary = f"从区域#{from_region_id}前往区域#{to_region_id} ({travel_time_seconds}s)"

    await record_decision(
        session,
        agent_id,
        DecisionType.TRAVEL,
        summary,
        context_snapshot={
            "from_region_id": from_region_id,
            "to_region_id": to_region_id,
            "travel_time_seconds": travel_time_seconds,
        },
        reference_type="travel",
        region_id=from_region_id,
    )


async def log_diplomacy_decision(
    session: AsyncSession,
    agent_id: int,
    *,
    action: str,
    target_agent_id: int | None = None,
    treaty_id: int | None = None,
    detail: str = "",
) -> None:
    """Log a diplomacy decision (called from diplomacy_svc)."""
    from agentropolis.services.decision_log_svc import record_decision

    summary = f"{action}: {detail}"

    await record_decision(
        session,
        agent_id,
        DecisionType.DIPLOMACY,
        summary,
        context_snapshot={
            "action": action,
            "target_agent_id": target_agent_id,
            "treaty_id": treaty_id,
        },
        reference_type="treaty" if treaty_id else None,
        reference_id=treaty_id,
    )


# ─── Strategy Modifier Helpers ─────────────────────────────────────────────


async def get_xp_modifier(session: AsyncSession, agent_id: int, skill_category: str) -> float:
    """Get XP gain multiplier for a skill, considering strategy profile focus.

    Called from skill_svc.award_xp() to adjust XP amounts.
    """
    from sqlalchemy import select

    from agentropolis.models.agent import Agent
    from agentropolis.services.career_svc import get_career_xp_multiplier
    from agentropolis.services.strategy_svc import get_profile, get_xp_multiplier

    profile = await get_profile(session, agent_id)
    agent = (
        await session.execute(select(Agent).where(Agent.id == agent_id))
    ).scalar_one_or_none()
    career_path = agent.career_path if agent is not None else None
    strategy_multiplier = get_xp_multiplier(profile, skill_category)
    career_multiplier = get_career_xp_multiplier(career_path, skill_category)
    return strategy_multiplier * career_multiplier


async def get_npc_price_modifier(session: AsyncSession, agent_id: int) -> float:
    """Get NPC shop price modifier from strategy + traits.

    Returns multiplier < 1.0 for discounts. Called from npc_shop_svc.
    """
    from agentropolis.services.strategy_svc import (
        get_profile,
        get_risk_modifiers,
        get_stance_modifiers,
    )
    from agentropolis.services.trait_svc import get_trait_bonus

    profile = await get_profile(session, agent_id)
    risk_mods = get_risk_modifiers(profile)
    stance_mods = get_stance_modifiers(profile)
    trait_discount = await get_trait_bonus(session, agent_id, "npc_price_discount")

    # Combine: risk discount * stance discount * trait discount
    modifier = risk_mods["npc_price_mult"] * (1.0 - stance_mods["npc_discount"]) * (1.0 - trait_discount)
    return max(0.5, modifier)  # floor at 50% discount


async def get_trade_tax_modifier(session: AsyncSession, agent_id: int) -> float:
    """Get trade tax modifier from traits.

    Returns multiplier < 1.0 for reduction. Called from market_engine.
    """
    from agentropolis.services.trait_svc import get_trait_bonus

    reduction = await get_trait_bonus(session, agent_id, "trade_tax_reduction")
    return max(0.0, 1.0 - reduction)


async def get_travel_time_modifier(session: AsyncSession, agent_id: int) -> float:
    """Get travel time modifier from ROAD_WARRIOR trait.

    Returns multiplier < 1.0 for faster travel. Called from world_svc.
    """
    from agentropolis.services.trait_svc import get_trait_bonus

    reduction = await get_trait_bonus(session, agent_id, "travel_time_reduction")
    return max(0.5, 1.0 - reduction)  # floor at 50% reduction


async def get_production_speed_modifier(session: AsyncSession, agent_id: int) -> float:
    """Get production speed modifier from SUPPLY_MASTER trait.

    Returns multiplier > 1.0 for faster production. Called from production service.
    """
    from agentropolis.services.trait_svc import get_production_trait_bonus

    bonus = await get_production_trait_bonus(session, agent_id)
    return 1.0 + bonus


async def get_mining_output_modifier(session: AsyncSession, agent_id: int) -> float:
    """Get NXC mining output modifier from NXC_TYCOON trait.

    Returns multiplier > 1.0 for bonus output. Called from nxc_mining_svc.
    """
    from agentropolis.services.trait_svc import get_mining_trait_bonus

    bonus = await get_mining_trait_bonus(session, agent_id)
    return 1.0 + bonus


async def get_respawn_balance_modifier(session: AsyncSession, agent_id: int) -> float:
    """Get respawn balance keep modifier from PHOENIX trait.

    Returns fraction of balance to keep (higher = better). Called from agent_svc.
    """
    from agentropolis.services.trait_svc import get_trait_bonus

    bonus = await get_trait_bonus(session, agent_id, "respawn_balance_keep")
    return bonus  # 0.0 if no trait, up to 0.50 at gold
