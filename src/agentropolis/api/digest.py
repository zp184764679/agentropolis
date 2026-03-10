"""Digest endpoints for autonomy-aware summaries."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from agentropolis.api.auth import get_current_agent
from agentropolis.api.preview_guard import (
    make_agent_preview_access_guard,
    make_agent_preview_write_guard,
    require_preview_surface,
)
from agentropolis.api.schemas import DigestAckResponse, DigestResponse
from agentropolis.database import get_session
from agentropolis.models import Agent
from agentropolis.services.concurrency import acquire_entity_locks, agent_lock_key
from agentropolis.services.digest_svc import acknowledge_digest_for_agent, build_digest

router = APIRouter(
    prefix="/digest",
    tags=["digest"],
    dependencies=[Depends(require_preview_surface)],
)
strategy_access_guard = make_agent_preview_access_guard("strategy")
strategy_write_guard = make_agent_preview_write_guard(
    "strategy",
    operation="digest_acknowledge",
)


@router.get("", response_model=DigestResponse)
async def read_digest(
    _guard: None = Depends(strategy_access_guard),
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_session),
):
    return await build_digest(session, agent.id)


@router.post("/ack", response_model=DigestAckResponse)
async def acknowledge_digest(
    _guard: None = Depends(strategy_write_guard),
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_session),
):
    async with acquire_entity_locks([agent_lock_key(agent.id)]):
        payload = await acknowledge_digest_for_agent(session, agent.id)
        await session.commit()
        return payload
