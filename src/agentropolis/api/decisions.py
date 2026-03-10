"""Decision Journal REST API endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from agentropolis.api.auth import get_current_agent
from agentropolis.api.preview_guard import require_preview_surface
from agentropolis.api.schemas import DecisionAnalysisResponse, DecisionLogResponse
from agentropolis.database import get_session
from agentropolis.models import Agent
from agentropolis.services.decision_log_svc import get_decision_analysis, get_recent_decisions

router = APIRouter(
    prefix="/agent/decisions",
    tags=["decisions"],
    dependencies=[Depends(require_preview_surface)],
)


@router.get("", response_model=DecisionLogResponse)
async def list_decisions(
    limit: int = Query(default=50, ge=1, le=200),
    decision_type: str | None = Query(default=None, description="Filter by type: TRADE, COMBAT, etc."),
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_session),
):
    """Get your recent decisions with outcomes."""
    try:
        entries = await get_recent_decisions(
            session,
            agent.id,
            limit=limit,
            decision_type=decision_type,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return {"entries": entries}


@router.get("/analysis", response_model=DecisionAnalysisResponse)
async def analyze_decisions(
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_session),
):
    """Get analysis of your decision history: win rates, avg ROI, best/worst decisions."""
    return await get_decision_analysis(session, agent.id)
