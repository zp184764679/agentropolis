"""Strategy Profile REST API endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentropolis.api.auth import get_current_agent
from agentropolis.api.preview_guard import (
    make_agent_preview_access_guard,
    make_agent_preview_write_guard,
    require_preview_surface,
)
from agentropolis.api.schemas import (
    StandingOrdersResponse,
    StrategyProfileResponse,
    StrategyProfileUpdateRequest,
    StrategyPublicProfileResponse,
    TrainingDashboardResponse,
)
from agentropolis.database import get_session
from agentropolis.models import Agent
from agentropolis.models.strategy_profile import StrategyProfile
from agentropolis.services.concurrency import acquire_entity_locks, agent_lock_key
from agentropolis.services.strategy_svc import (
    create_or_update_profile,
    get_combat_modifiers,
    get_profile,
    get_public_profile,
    get_risk_modifiers,
    get_xp_multiplier,
)

router = APIRouter(
    prefix="/strategy",
    tags=["strategy"],
    dependencies=[Depends(require_preview_surface)],
)
strategy_write_guard = make_agent_preview_write_guard(
    "strategy",
    operation="strategy_profile_update",
)
strategy_access_guard = make_agent_preview_access_guard("strategy")


@router.get("/profile", response_model=StrategyProfileResponse)
async def get_my_profile(
    _guard: None = Depends(strategy_access_guard),
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_session),
):
    """Get your strategy profile (full view including risk_tolerance)."""
    profile = await get_profile(session, agent.id)
    if profile is None:
        # Create default profile
        result = await create_or_update_profile(session, agent.id)
        await session.commit()
        return result
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


@router.put(
    "/profile",
    response_model=StrategyProfileResponse,
    dependencies=[Depends(strategy_write_guard)],
)
async def update_profile(
    req: StrategyProfileUpdateRequest,
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_session),
):
    """Update your strategy profile. Only send fields you want to change."""
    try:
        async with acquire_entity_locks([agent_lock_key(agent.id)]):
            result = await create_or_update_profile(
                session,
                agent.id,
                combat_doctrine=req.combat_doctrine,
                risk_tolerance=req.risk_tolerance,
                primary_focus=req.primary_focus,
                secondary_focus=req.secondary_focus,
                default_stance=req.default_stance,
            )
            await session.commit()
            return result
    except ValueError as e:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(e)) from None


@router.get("/scout/{agent_id}", response_model=StrategyPublicProfileResponse)
async def scout_agent(
    agent_id: int,
    _guard: None = Depends(strategy_access_guard),
    _agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_session),
):
    """Scout another agent's public strategy profile.

    Shows doctrine, focus, stance, standing orders — but NOT risk_tolerance.
    """
    profile = await get_public_profile(session, agent_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Agent has no strategy profile")
    return profile


@router.get("/dashboard", response_model=TrainingDashboardResponse)
async def training_dashboard(
    _guard: None = Depends(strategy_access_guard),
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_session),
):
    """Comprehensive training dashboard: profile + active modifiers + traits + decision summary.

    This is the main "coaching screen" where you see everything about your agent's configuration
    and how it translates into actual game mechanics.
    """
    from agentropolis.services.decision_log_svc import get_decision_analysis
    from agentropolis.services.strategy_svc import FOCUS_SKILLS, get_stance_modifiers
    from agentropolis.services.trait_svc import get_agent_traits, get_combat_trait_modifiers

    profile = await get_profile(session, agent.id)
    if profile is None:
        await create_or_update_profile(session, agent.id)
        await session.commit()
        profile = await get_profile(session, agent.id)

    # Compute active modifiers
    combat_mods = get_combat_modifiers(profile)
    risk_mods = get_risk_modifiers(profile)
    stance_mods = get_stance_modifiers(profile)

    # XP multipliers for all skill categories
    xp_mults = {}
    for _focus, skills in FOCUS_SKILLS.items():
        for skill in skills:
            xp_mults[skill] = get_xp_multiplier(profile, skill)

    # Trait bonuses
    traits = await get_agent_traits(session, agent.id)
    trait_combat = await get_combat_trait_modifiers(session, agent.id)

    # Decision analysis
    analysis = await get_decision_analysis(session, agent.id)

    return {
        "agent_id": agent.id,
        "agent_name": agent.name,
        "profile": {
            "combat_doctrine": profile.combat_doctrine.value,
            "risk_tolerance": profile.risk_tolerance,
            "primary_focus": profile.primary_focus.value,
            "secondary_focus": profile.secondary_focus.value if profile.secondary_focus else None,
            "default_stance": profile.default_stance.value,
            "standing_orders": profile.standing_orders,
            "version": profile.version,
        },
        "active_modifiers": {
            "combat": {
                "attack_mult": round(combat_mods["attack_mult"] * (1.0 + trait_combat["attack_bonus"]), 3),
                "defense_mult": round(combat_mods["defense_mult"] * (1.0 + trait_combat["defense_bonus"]), 3),
                "doctrine_attack": combat_mods["attack_mult"],
                "doctrine_defense": combat_mods["defense_mult"],
                "trait_attack_bonus": trait_combat["attack_bonus"],
                "trait_defense_bonus": trait_combat["defense_bonus"],
            },
            "economy": {
                "trade_profit_mult": risk_mods["trade_profit_mult"],
                "damage_taken_mult": risk_mods["damage_taken_mult"],
                "npc_price_mult": risk_mods["npc_price_mult"],
                "stance_raid_loot_mult": stance_mods["raid_loot_mult"],
                "stance_npc_discount": stance_mods["npc_discount"],
            },
            "xp_multipliers": xp_mults,
        },
        "traits": traits,
        "decision_summary": analysis,
    }


@router.get("/standing-orders", response_model=StandingOrdersResponse)
async def list_standing_orders(
    region_id: int | None = Query(default=None, description="Filter by region"),
    _guard: None = Depends(strategy_access_guard),
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_session),
):
    """List all agents' standing orders (public intelligence mirror).

    Canonical standing-order writes live under `/api/autonomy/standing-orders`.
    This route exposes the mirrored public scouting view that other players can
    read before trading.
    """
    from agentropolis.models.agent import Agent as AgentModel

    query = (
        select(StrategyProfile, AgentModel.name, AgentModel.current_region_id)
        .join(AgentModel, StrategyProfile.agent_id == AgentModel.id)
        .where(
            StrategyProfile.standing_orders.is_not(None),
            AgentModel.is_active.is_(True),
        )
    )

    if region_id is not None:
        query = query.where(AgentModel.current_region_id == region_id)

    result = await session.execute(query)
    rows = result.all()

    return {
        "standing_orders": [
            {
                "agent_id": profile.agent_id,
                "agent_name": name,
                "current_region_id": current_region,
                "combat_doctrine": profile.combat_doctrine.value,
                "standing_orders": profile.standing_orders,
            }
            for profile, name, current_region in rows
        ],
    }
