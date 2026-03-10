"""World REST API endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from agentropolis.api.auth import get_current_agent
from agentropolis.api.preview_guard import (
    make_agent_preview_access_guard,
    make_agent_preview_write_guard,
    require_preview_surface,
)
from agentropolis.api.schemas import (
    RegionInfo,
    TravelRequest,
    TravelStatus,
    WorldMapResponse,
)
from agentropolis.database import get_session
from agentropolis.models import Agent
from agentropolis.services.concurrency import acquire_entity_locks, agent_lock_key
from agentropolis.services.world_svc import (
    get_all_regions,
    get_region as get_region_svc,
    get_travel_status as get_travel_status_svc,
    start_travel as start_travel_svc,
)

router = APIRouter(
    prefix="/world",
    tags=["world"],
    dependencies=[Depends(require_preview_surface)],
)
world_write_guard = make_agent_preview_write_guard(
    "world",
    operation="travel_start",
)
world_access_guard = make_agent_preview_access_guard("world")


@router.get("/map", response_model=WorldMapResponse)
async def get_world_map(session: AsyncSession = Depends(get_session)):
    """Get the complete world map with all regions and connections."""
    return {"regions": await get_all_regions(session)}


@router.get("/region/{region_id}", response_model=RegionInfo)
async def get_region(region_id: int, session: AsyncSession = Depends(get_session)):
    """Get info about a specific region."""
    try:
        return await get_region_svc(session, region_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None


@router.post(
    "/travel",
    response_model=TravelStatus,
    dependencies=[Depends(world_write_guard)],
)
async def start_travel(
    req: TravelRequest,
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_session),
):
    """Start traveling to another region."""
    try:
        async with acquire_entity_locks([agent_lock_key(agent.id)]):
            result = await start_travel_svc(session, agent.id, req.to_region_id)
            await session.commit()
            return result
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from None


@router.get("/travel/status", response_model=TravelStatus)
async def get_travel_status(
    _guard: None = Depends(world_access_guard),
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_session),
):
    """Get current travel status."""
    result = await get_travel_status_svc(session, agent.id)
    await session.commit()
    if result is None:
        raise HTTPException(status_code=404, detail="Agent is not currently traveling")
    return result
