"""Real-time dashboard endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from agentropolis.api.auth import get_current_agent
from agentropolis.api.preview_guard import (
    make_agent_preview_access_guard,
    require_preview_surface,
)
from agentropolis.api.schemas import DashboardResponse
from agentropolis.database import get_session
from agentropolis.models import Agent
from agentropolis.services.digest_svc import build_dashboard

router = APIRouter(
    prefix="/dashboard",
    tags=["dashboard"],
    dependencies=[Depends(require_preview_surface)],
)
strategy_access_guard = make_agent_preview_access_guard("strategy")


@router.get("", response_model=DashboardResponse)
async def read_dashboard(
    _guard: None = Depends(strategy_access_guard),
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_session),
):
    return await build_dashboard(session, agent.id)
