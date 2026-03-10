"""Transport REST API endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from agentropolis.api.auth import get_current_agent
from agentropolis.api.preview_guard import (
    make_agent_preview_access_guard,
    make_agent_preview_write_guard,
    require_preview_surface,
)
from agentropolis.api.schemas import TransportRequest, TransportStatusResponse
from agentropolis.database import get_session
from agentropolis.models import Agent
from agentropolis.services.transport_svc import (
    create_transport as create_transport_svc,
    get_my_transports as get_my_transports_svc,
    get_transport_status as get_transport_status_svc,
)

router = APIRouter(
    prefix="/transport",
    tags=["transport"],
    dependencies=[Depends(require_preview_surface)],
)
transport_write_guard = make_agent_preview_write_guard("transport")
transport_access_guard = make_agent_preview_access_guard("transport")


@router.post(
    "/create",
    response_model=TransportStatusResponse,
    dependencies=[Depends(transport_write_guard)],
)
async def create_transport(
    req: TransportRequest,
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_session),
):
    """Create a transport order to move items between regions."""
    try:
        result = await create_transport_svc(
            session,
            req.from_region_id,
            req.to_region_id,
            req.items,
            req.transport_type,
            agent_id=agent.id,
        )
        await session.commit()
        return result
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from None


@router.get("/status/{transport_id}", response_model=TransportStatusResponse)
async def get_transport_status(
    transport_id: int,
    _guard: None = Depends(transport_access_guard),
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_session),
):
    """Get status of a transport order."""
    try:
        result = await get_transport_status_svc(session, transport_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None

    if result["owner_agent_id"] != agent.id:
        raise HTTPException(status_code=404, detail="Transport not found")
    return result


@router.get("/mine", response_model=list[TransportStatusResponse])
async def get_my_transports(
    _guard: None = Depends(transport_access_guard),
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_session),
):
    """Get all your transport orders."""
    return await get_my_transports_svc(session, agent_id=agent.id)
