"""Rich information endpoints for AI decision support."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from agentropolis.api.auth import get_current_agent
from agentropolis.api.preview_guard import (
    ERROR_CODE_HEADER,
    make_agent_preview_access_guard,
    require_preview_surface,
)
from agentropolis.api.schemas import MarketIntelResponse, OpportunityResponse, RouteIntelResponse
from agentropolis.database import get_session
from agentropolis.models import Agent
from agentropolis.services.market_analysis_svc import (
    get_market_intel,
    get_opportunities,
    get_route_intel,
)

router = APIRouter(
    prefix="/intel",
    tags=["intel"],
    dependencies=[Depends(require_preview_surface)],
)
strategy_access_guard = make_agent_preview_access_guard("strategy")


@router.get("/market/{ticker}", response_model=MarketIntelResponse)
async def read_market_intel(
    ticker: str,
    _guard: None = Depends(strategy_access_guard),
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_session),
):
    try:
        return await get_market_intel(session, agent.id, ticker)
    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
            headers={ERROR_CODE_HEADER: "market_resource_not_found"},
        ) from None


@router.get("/routes", response_model=RouteIntelResponse)
async def read_route_intel(
    to_region_id: int = Query(..., gt=0),
    _guard: None = Depends(strategy_access_guard),
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_session),
):
    try:
        return await get_route_intel(session, agent.id, to_region_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
            headers={ERROR_CODE_HEADER: "world_route_not_found"},
        ) from None


@router.get("/opportunities", response_model=OpportunityResponse)
async def read_opportunities(
    _guard: None = Depends(strategy_access_guard),
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_session),
):
    return await get_opportunities(session, agent.id)
