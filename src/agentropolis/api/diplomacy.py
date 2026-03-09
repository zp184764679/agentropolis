"""Diplomacy REST API endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from agentropolis.api.auth import get_current_agent
from agentropolis.api.schemas import SuccessResponse, TreatyInfo
from agentropolis.database import get_session
from agentropolis.models import Agent

router = APIRouter(prefix="/diplomacy", tags=["diplomacy"])


@router.post("/treaty/propose", response_model=TreatyInfo)
async def propose_treaty(
    treaty_type: str,
    target_agent_id: int | None = None,
    target_guild_id: int | None = None,
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_session),
):
    """Propose a treaty."""
    raise NotImplementedError("Issue #34: Implement diplomacy API endpoints")


@router.post("/treaty/{treaty_id}/accept", response_model=TreatyInfo)
async def accept_treaty(
    treaty_id: int,
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_session),
):
    """Accept a proposed treaty."""
    raise NotImplementedError("Issue #34: Implement diplomacy API endpoints")


@router.get("/treaties", response_model=list[TreatyInfo])
async def get_treaties(
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_session),
):
    """Get all treaties involving you."""
    raise NotImplementedError("Issue #34: Implement diplomacy API endpoints")


@router.post("/relationship", response_model=SuccessResponse)
async def set_relationship(
    target_agent_id: int,
    relation_type: str,
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_session),
):
    """Set your relationship with another agent."""
    raise NotImplementedError("Issue #34: Implement diplomacy API endpoints")
