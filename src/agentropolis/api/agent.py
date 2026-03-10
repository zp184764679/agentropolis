"""Agent REST API endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentropolis.api.auth import get_current_agent
from agentropolis.api.preview_guard import (
    make_agent_preview_access_guard,
    make_agent_preview_write_guard,
    require_preview_registration_write,
    require_preview_surface,
)
from agentropolis.api.schemas import (
    AgentCompanyCreateRequest,
    AgentCompanyCreateResponse,
    AgentPublicProfile,
    AgentRegisterRequest,
    AgentRegisterResponse,
    AgentStatus,
    BuildingInfo,
    CompanyStatus,
    SuccessResponse,
    WorkerInfo,
)
from agentropolis.database import get_session
from agentropolis.models import Agent
from agentropolis.services.concurrency import acquire_entity_locks, agent_lock_key
from agentropolis.services.agent_svc import (
    drink as drink_agent,
    eat as eat_agent,
    get_agent_status,
    register_agent as register_agent_svc,
    rest as rest_agent,
)
from agentropolis.services.company_svc import (
    get_agent_company,
    get_company_workers,
    register_company as register_company_svc,
)
from agentropolis.services.production import get_agent_company_buildings
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
agent_self_access_guard = make_agent_preview_access_guard("agent_self")


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


@router.post(
    "/company",
    response_model=AgentCompanyCreateResponse,
    dependencies=[Depends(agent_self_write_guard)],
)
async def register_company(
    req: AgentCompanyCreateRequest,
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_session),
):
    """Create the current agent's company and receive its company API key."""
    try:
        async with acquire_entity_locks([agent_lock_key(agent.id)]):
            result = await register_company_svc(
                session,
                req.company_name,
                founder_agent_id=agent.id,
            )
            await session.commit()
            return result
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from None


@router.get(
    "/company",
    response_model=CompanyStatus,
    dependencies=[Depends(agent_self_access_guard)],
)
async def get_my_company(
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_session),
):
    """Get the active company owned by the current agent."""
    company = await get_agent_company(session, agent.id)
    if company is None:
        raise HTTPException(status_code=404, detail="Agent does not have an active company")
    return company


@router.get(
    "/company/workers",
    response_model=WorkerInfo,
    dependencies=[Depends(agent_self_access_guard)],
)
async def get_my_company_workers(
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_session),
):
    """Get workforce details for the current agent's company."""
    company = await get_agent_company(session, agent.id)
    if company is None:
        raise HTTPException(status_code=404, detail="Agent does not have an active company")
    return await get_company_workers(session, company["company_id"])


@router.get(
    "/company/buildings",
    response_model=list[BuildingInfo],
    dependencies=[Depends(agent_self_access_guard)],
)
async def get_my_company_buildings(
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_session),
):
    """List the current agent's company buildings."""
    try:
        return await get_agent_company_buildings(session, agent.id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None


@router.get("/status", response_model=AgentStatus)
async def get_status(
    _guard: None = Depends(agent_self_access_guard),
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
        async with acquire_entity_locks([agent_lock_key(agent.id)]):
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
        async with acquire_entity_locks([agent_lock_key(agent.id)]):
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
        async with acquire_entity_locks([agent_lock_key(agent.id)]):
            result = await rest_agent(session, agent.id)
            await session.commit()
            return {"message": f"Rested. Energy is now {result['energy']:.1f}."}
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from None


@router.get("/profile/{agent_id}", response_model=AgentPublicProfile)
async def get_public_agent_profile(
    agent_id: int,
    _guard: None = Depends(agent_self_access_guard),
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
