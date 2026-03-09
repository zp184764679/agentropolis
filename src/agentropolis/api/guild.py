"""Guild REST API endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from agentropolis.api.auth import get_current_agent
from agentropolis.api.schemas import GuildCreateRequest, GuildInfo, SuccessResponse
from agentropolis.database import get_session
from agentropolis.models import Agent

router = APIRouter(prefix="/guild", tags=["guild"])


@router.post("/create", response_model=GuildInfo)
async def create_guild(
    req: GuildCreateRequest,
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_session),
):
    """Create a new guild."""
    raise NotImplementedError("Issue #34: Implement guild API endpoints")


@router.get("/{guild_id}", response_model=GuildInfo)
async def get_guild(
    guild_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Get guild info."""
    raise NotImplementedError("Issue #34: Implement guild API endpoints")


@router.post("/{guild_id}/join", response_model=SuccessResponse)
async def join_guild(
    guild_id: int,
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_session),
):
    """Join a guild."""
    raise NotImplementedError("Issue #34: Implement guild API endpoints")


@router.post("/{guild_id}/leave", response_model=SuccessResponse)
async def leave_guild(
    guild_id: int,
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_session),
):
    """Leave a guild."""
    raise NotImplementedError("Issue #34: Implement guild API endpoints")
