"""Guild REST API endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from agentropolis.api.auth import get_current_agent
from agentropolis.api.preview_guard import (
    make_agent_preview_write_guard,
    require_preview_surface,
)
from agentropolis.api.schemas import (
    GuildCreateRequest,
    GuildDepositRequest,
    GuildInfo,
    GuildPromoteRequest,
    SuccessResponse,
)
from agentropolis.database import get_session
from agentropolis.models import Agent
from agentropolis.services.concurrency import (
    acquire_entity_locks,
    agent_lock_key,
    guild_lock_key,
)
from agentropolis.services.guild_svc import (
    create_guild as create_guild_svc,
    deposit_to_treasury,
    disband_guild,
    get_guild_info,
    join_guild as join_guild_svc,
    leave_guild as leave_guild_svc,
    list_guilds,
    promote_member,
)

router = APIRouter(
    prefix="/guild",
    tags=["guild"],
    dependencies=[Depends(require_preview_surface)],
)
social_write_guard = make_agent_preview_write_guard("social")
guild_create_guard = make_agent_preview_write_guard("social", operation="guild_create")
guild_join_leave_guard = make_agent_preview_write_guard(
    "social",
    operation="guild_join_leave",
)
guild_promote_guard = make_agent_preview_write_guard("social", operation="guild_promote")
guild_disband_guard = make_agent_preview_write_guard("social", operation="guild_disband")


@router.post(
    "/create",
    response_model=GuildInfo,
    dependencies=[Depends(guild_create_guard)],
)
async def create_guild(
    req: GuildCreateRequest,
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_session),
):
    """Create a new guild."""
    try:
        async with acquire_entity_locks([agent_lock_key(agent.id)]):
            result = await create_guild_svc(session, agent.id, req.name, req.home_region_id)
            await session.commit()
            return result
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from None


@router.get("/{guild_id}", response_model=GuildInfo)
async def get_guild(
    guild_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Get guild info."""
    try:
        return await get_guild_info(session, guild_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None


@router.get("/list/all", response_model=list[GuildInfo])
async def list_all_guilds(
    region_id: int | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
):
    """List active guilds, optionally filtered by home region."""
    return await list_guilds(session, region_id=region_id)


@router.post(
    "/{guild_id}/join",
    response_model=SuccessResponse,
    dependencies=[Depends(guild_join_leave_guard)],
)
async def join_guild(
    guild_id: int,
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_session),
):
    """Join a guild."""
    try:
        async with acquire_entity_locks([agent_lock_key(agent.id), guild_lock_key(guild_id)]):
            result = await join_guild_svc(session, agent.id, guild_id)
            await session.commit()
            return {"message": f"Joined guild {result['guild_id']} as {result['rank']}."}
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from None


@router.post(
    "/{guild_id}/leave",
    response_model=SuccessResponse,
    dependencies=[Depends(guild_join_leave_guard)],
)
async def leave_guild(
    guild_id: int,
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_session),
):
    """Leave a guild."""
    try:
        async with acquire_entity_locks([agent_lock_key(agent.id), guild_lock_key(guild_id)]):
            await leave_guild_svc(session, agent.id, guild_id)
            await session.commit()
            return {"message": f"Left guild {guild_id}."}
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from None


@router.post(
    "/{guild_id}/promote",
    response_model=SuccessResponse,
    dependencies=[Depends(guild_promote_guard)],
)
async def promote_guild_member(
    guild_id: int,
    req: GuildPromoteRequest,
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_session),
):
    """Promote or demote a guild member."""
    try:
        async with acquire_entity_locks(
            [
                agent_lock_key(agent.id),
                agent_lock_key(req.agent_id),
                guild_lock_key(guild_id),
            ]
        ):
            result = await promote_member(
                session,
                agent.id,
                req.agent_id,
                guild_id,
                req.new_rank,
            )
            await session.commit()
            return {
                "message": f"Agent {result['agent_id']} rank set to {result['new_rank']}."
            }
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from None


@router.post(
    "/{guild_id}/deposit",
    response_model=SuccessResponse,
    dependencies=[Depends(social_write_guard)],
)
async def deposit_guild_treasury(
    guild_id: int,
    req: GuildDepositRequest,
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_session),
):
    """Deposit copper into the guild treasury."""
    try:
        async with acquire_entity_locks([agent_lock_key(agent.id), guild_lock_key(guild_id)]):
            treasury = await deposit_to_treasury(session, agent.id, guild_id, req.amount)
            await session.commit()
            return {"message": f"Deposited {req.amount} copper. Treasury is now {treasury}."}
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from None


@router.post(
    "/{guild_id}/disband",
    response_model=SuccessResponse,
    dependencies=[Depends(guild_disband_guard)],
)
async def disband(
    guild_id: int,
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_session),
):
    """Disband a guild and return treasury to the leader."""
    try:
        async with acquire_entity_locks([agent_lock_key(agent.id), guild_lock_key(guild_id)]):
            await disband_guild(session, agent.id, guild_id)
            await session.commit()
            return {"message": f"Guild {guild_id} disbanded."}
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from None
