"""Diplomacy REST API endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from agentropolis.api.auth import get_current_agent
from agentropolis.api.preview_guard import (
    require_agent_preview_write,
    require_preview_surface,
)
from agentropolis.api.schemas import (
    RelationshipInfo,
    RelationshipSetRequest,
    TreatyInfo,
    TreatyProposeRequest,
)
from agentropolis.database import get_session
from agentropolis.models import Agent
from agentropolis.services.diplomacy_svc import (
    accept_treaty as accept_treaty_svc,
    get_relationships,
    get_treaties,
    propose_treaty as propose_treaty_svc,
    set_relationship as set_relationship_svc,
)

router = APIRouter(
    prefix="/diplomacy",
    tags=["diplomacy"],
    dependencies=[Depends(require_preview_surface)],
)


@router.post(
    "/treaty/propose",
    response_model=TreatyInfo,
    dependencies=[Depends(require_agent_preview_write)],
)
async def propose_treaty(
    req: TreatyProposeRequest,
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_session),
):
    """Propose a treaty."""
    try:
        result = await propose_treaty_svc(
            session,
            req.treaty_type,
            party_a_agent_id=agent.id,
            party_b_agent_id=req.target_agent_id,
            party_b_guild_id=req.target_guild_id,
            terms=req.terms,
            duration_hours=req.duration_hours,
        )
        await session.commit()
        return result
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from None


@router.post(
    "/treaty/{treaty_id}/accept",
    response_model=TreatyInfo,
    dependencies=[Depends(require_agent_preview_write)],
)
async def accept_treaty(
    treaty_id: int,
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_session),
):
    """Accept a proposed treaty."""
    try:
        result = await accept_treaty_svc(session, treaty_id, agent.id)
        await session.commit()
        return result
    except ValueError as exc:
        await session.rollback()
        status_code = 404 if "not found" in str(exc).lower() else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from None


@router.get("/treaties", response_model=list[TreatyInfo])
async def get_agent_treaties(
    active_only: bool = Query(default=True),
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_session),
):
    """Get all treaties involving you."""
    return await get_treaties(session, agent_id=agent.id, active_only=active_only)


@router.get("/relationships", response_model=list[RelationshipInfo])
async def list_relationships(
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_session),
):
    """Get your relationships with other agents."""
    return await get_relationships(session, agent.id)


@router.post(
    "/relationship",
    response_model=RelationshipInfo,
    dependencies=[Depends(require_agent_preview_write)],
)
async def set_relationship(
    req: RelationshipSetRequest,
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_session),
):
    """Set your relationship with another agent."""
    try:
        result = await set_relationship_svc(
            session,
            agent.id,
            req.target_agent_id,
            req.relation_type,
            trust_delta=req.trust_delta,
        )
        await session.commit()
        return result
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from None
