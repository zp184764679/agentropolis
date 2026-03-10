"""Agent REST API endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentropolis.api.auth import get_current_agent
from agentropolis.api.preview_guard import (
    make_agent_preview_write_guard,
    require_preview_registration_write,
    require_preview_surface,
)
from agentropolis.api.schemas import (
    AgentPublicProfile,
    AgentRegisterRequest,
    AgentRegisterResponse,
    AgentStatus,
    SuccessResponse,
)
from agentropolis.database import get_session
from agentropolis.models import Agent
from agentropolis.services.agent_svc import (
    drink as drink_agent,
    eat as eat_agent,
    get_agent_status,
    register_agent as register_agent_svc,
    rest as rest_agent,
)
from agentropolis.services.strategy_svc import get_public_profile
from agentropolis.services.trait_svc import get_agent_traits

router = APIRouter(
    prefix="/agent",
    tags=["agent"],
    dependencies=[Depends(require_preview_surface)],
)
agent_self_write_guard = make_agent_preview_write_guard(
    "agent_self",
    allow_in_degraded_mode=True,
)


@router.post(
    "/register",
    response_model=AgentRegisterResponse,
    dependencies=[Depends(require_preview_registration_write)],
)
async def register_agent(
    req: AgentRegisterRequest, session: AsyncSession = Depends(get_session)
):
    """Register a new agent and get your API key."""
    try:
        result = await register_agent_svc(session, req.name, req.home_region_id)
        await session.commit()
        return result
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from None


@router.get("/status", response_model=AgentStatus)
async def get_status(
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_session),
):
    """Get your agent's current status with settled vitals."""
    try:
        result = await get_agent_status(session, agent.id)
        await session.commit()
        return result
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from None


@router.post(
    "/eat",
    response_model=SuccessResponse,
    dependencies=[Depends(agent_self_write_guard)],
)
async def eat(
    amount: int = 1,
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_session),
):
    """Eat rations to replenish hunger."""
    try:
        result = await eat_agent(session, agent.id, amount=amount)
        await session.commit()
        return {
            "message": (
                f"Ate {result['consumed']} RAT. Hunger is now "
                f"{result['status']['hunger']:.1f}."
            )
        }
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from None


@router.post(
    "/drink",
    response_model=SuccessResponse,
    dependencies=[Depends(agent_self_write_guard)],
)
async def drink(
    amount: int = 1,
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_session),
):
    """Drink water to replenish thirst."""
    try:
        result = await drink_agent(session, agent.id, amount=amount)
        await session.commit()
        return {
            "message": (
                f"Drank {result['consumed']} DW. Thirst is now "
                f"{result['status']['thirst']:.1f}."
            )
        }
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from None


@router.post(
    "/rest",
    response_model=SuccessResponse,
    dependencies=[Depends(agent_self_write_guard)],
)
async def rest(
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_session),
):
    """Rest to replenish energy."""
    try:
        result = await rest_agent(session, agent.id)
        await session.commit()
        return {"message": f"Rested. Energy is now {result['energy']:.1f}."}
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from None


@router.get("/profile/{agent_id}", response_model=AgentPublicProfile)
async def get_public_agent_profile(
    agent_id: int,
    _agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_session),
):
    """View another agent's public profile including strategy and traits."""
    result = await session.execute(select(Agent).where(Agent.id == agent_id))
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="Agent not found")

    strategy = await get_public_profile(session, agent_id)
    traits = await get_agent_traits(session, agent_id)

    return {
        "agent_id": target.id,
        "name": target.name,
        "reputation": target.reputation,
        "is_alive": target.is_alive,
        "current_region_id": target.current_region_id,
        "career_path": target.career_path,
        "strategy": strategy,
        "traits": traits,
    }
