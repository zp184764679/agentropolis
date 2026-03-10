"""Autonomy config and goal management endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from agentropolis.api.auth import get_current_agent
from agentropolis.api.preview_guard import (
    ERROR_CODE_HEADER,
    make_agent_preview_access_guard,
    make_agent_preview_write_guard,
    require_preview_surface,
)
from agentropolis.api.schemas import (
    AutonomyStandingOrdersResponse,
    AutonomyConfigResponse,
    AutonomyConfigUpdateRequest,
    GoalCreateRequest,
    GoalListResponse,
    GoalResponse,
    GoalUpdateRequest,
    StandingOrdersUpdateRequest,
)
from agentropolis.database import get_session
from agentropolis.models import Agent
from agentropolis.services.concurrency import acquire_entity_locks, agent_lock_key
from agentropolis.services.autopilot import (
    get_autonomy_config,
    get_standing_orders,
    update_autonomy_config,
    update_standing_orders,
)
from agentropolis.services.goal_svc import create_goal, list_goals, update_goal

router = APIRouter(
    prefix="/autonomy",
    tags=["autonomy"],
    dependencies=[Depends(require_preview_surface)],
)
strategy_access_guard = make_agent_preview_access_guard("strategy")
autonomy_config_guard = make_agent_preview_write_guard(
    "strategy",
    operation="autonomy_config_update",
)
standing_orders_guard = make_agent_preview_write_guard(
    "strategy",
    operation="standing_order_replace",
)
goal_write_guard = make_agent_preview_write_guard(
    "strategy",
    operation="goal_create_update",
)


@router.get("/config", response_model=AutonomyConfigResponse)
async def read_autonomy_config(
    _guard: None = Depends(strategy_access_guard),
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_session),
):
    return await get_autonomy_config(session, agent.id)


@router.put(
    "/config",
    response_model=AutonomyConfigResponse,
    dependencies=[Depends(autonomy_config_guard)],
)
async def write_autonomy_config(
    req: AutonomyConfigUpdateRequest,
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_session),
):
    try:
        async with acquire_entity_locks([agent_lock_key(agent.id)]):
            payload = await update_autonomy_config(
                session,
                agent.id,
                autopilot_enabled=req.autopilot_enabled,
                mode=req.mode,
                spending_limit_per_hour=req.spending_limit_per_hour,
            )
            await session.commit()
            return payload
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=400,
            detail=str(exc),
            headers={ERROR_CODE_HEADER: "autonomy_config_invalid"},
        ) from None


@router.get("/standing-orders", response_model=AutonomyStandingOrdersResponse)
async def read_standing_orders(
    _guard: None = Depends(strategy_access_guard),
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_session),
):
    payload = await get_standing_orders(session, agent.id)
    return {"agent_id": agent.id, "standing_orders": payload}


@router.put(
    "/standing-orders",
    response_model=AutonomyStandingOrdersResponse,
    dependencies=[Depends(standing_orders_guard)],
)
async def write_standing_orders(
    req: StandingOrdersUpdateRequest,
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_session),
):
    try:
        async with acquire_entity_locks([agent_lock_key(agent.id)]):
            payload = await update_standing_orders(
                session,
                agent.id,
                req.standing_orders.model_dump(),
            )
            await session.commit()
            return {"agent_id": agent.id, "standing_orders": payload}
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=422,
            detail=str(exc),
            headers={ERROR_CODE_HEADER: "autonomy_rule_unsupported"},
        ) from None


@router.get("/goals", response_model=GoalListResponse)
async def read_goals(
    _guard: None = Depends(strategy_access_guard),
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_session),
):
    return {"goals": await list_goals(session, agent.id)}


@router.post(
    "/goals",
    response_model=GoalResponse,
    dependencies=[Depends(goal_write_guard)],
)
async def create_autonomy_goal(
    req: GoalCreateRequest,
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_session),
):
    try:
        async with acquire_entity_locks([agent_lock_key(agent.id)]):
            payload = await create_goal(
                session,
                agent.id,
                goal_type=req.goal_type,
                priority=req.priority,
                target=req.target,
                notes=req.notes,
            )
            await session.commit()
            return payload
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=400,
            detail=str(exc),
            headers={ERROR_CODE_HEADER: "autonomy_goal_invalid"},
        ) from None


@router.patch(
    "/goals/{goal_id}",
    response_model=GoalResponse,
    dependencies=[Depends(goal_write_guard)],
)
async def patch_goal(
    goal_id: int,
    req: GoalUpdateRequest,
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_session),
):
    try:
        async with acquire_entity_locks([agent_lock_key(agent.id)]):
            payload = await update_goal(
                session,
                agent.id,
                goal_id,
                status=req.status,
                priority=req.priority,
                target=req.target,
                progress=req.progress,
                notes=req.notes,
            )
            await session.commit()
            return payload
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=400,
            detail=str(exc),
            headers={ERROR_CODE_HEADER: "autonomy_goal_invalid"},
        ) from None
