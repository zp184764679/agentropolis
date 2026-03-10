"""Diplomacy REST API endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from agentropolis.api.auth import get_current_agent
from agentropolis.api.preview_guard import (
    make_agent_preview_access_guard,
    make_agent_preview_write_guard,
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
from agentropolis.services.concurrency import (
    acquire_entity_locks,
    agent_lock_key,
    guild_lock_key,
    treaty_lock_key,
)
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
social_write_guard = make_agent_preview_write_guard("social")
social_treaty_guard = make_agent_preview_write_guard(
    "social",
    operation="treaty_propose_accept",
)
social_relationship_guard = make_agent_preview_write_guard(
    "social",
    operation="relationship_set",
)
social_access_guard = make_agent_preview_access_guard("social")


@router.post(
    "/treaty/propose",
    response_model=TreatyInfo,
    dependencies=[Depends(social_treaty_guard)],
)
async def propose_treaty(
    req: TreatyProposeRequest,
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_session),
):
    """Propose a treaty."""
    try:
        lock_keys = [agent_lock_key(agent.id)]
        if req.target_agent_id is not None:
            lock_keys.append(agent_lock_key(req.target_agent_id))
        if req.target_guild_id is not None:
            lock_keys.append(guild_lock_key(req.target_guild_id))
        async with acquire_entity_locks(lock_keys):
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
    dependencies=[Depends(social_treaty_guard)],
)
async def accept_treaty(
    treaty_id: int,
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_session),
):
    """Accept a proposed treaty."""
    try:
        async with acquire_entity_locks([agent_lock_key(agent.id), treaty_lock_key(treaty_id)]):
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
    _guard: None = Depends(social_access_guard),
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_session),
):
    """Get all treaties involving you."""
    return await get_treaties(session, agent_id=agent.id, active_only=active_only)


@router.get("/relationships", response_model=list[RelationshipInfo])
async def list_relationships(
    _guard: None = Depends(social_access_guard),
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_session),
):
    """Get your relationships with other agents."""
    return await get_relationships(session, agent.id)


@router.post(
    "/relationship",
    response_model=RelationshipInfo,
    dependencies=[Depends(social_relationship_guard)],
)
async def set_relationship(
    req: RelationshipSetRequest,
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_session),
):
    """Set your relationship with another agent."""
    try:
        async with acquire_entity_locks(
            [agent_lock_key(agent.id), agent_lock_key(req.target_agent_id)]
        ):
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
