"""Warfare REST API endpoints - mercenary contracts, combat, garrison, repair."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from agentropolis.api.auth import get_current_agent
from agentropolis.api.preview_guard import (
    require_preview_surface,
    require_warfare_preview_write,
)
from agentropolis.api.schemas import (
    ContractExecutionResponse,
    ContractCreateRequest,
    ContractDetailResponse,
    ContractListResponse,
    GarrisonResponse,
    RegionThreatResponse,
    RepairResponse,
    SuccessResponse,
)
from agentropolis.database import get_session
from agentropolis.models import Agent
from agentropolis.services.concurrency import (
    acquire_entity_locks,
    agent_lock_key,
    building_lock_key,
    contract_lock_key,
)
from agentropolis.services import warfare_svc

router = APIRouter(
    prefix="/warfare",
    tags=["warfare"],
    dependencies=[Depends(require_preview_surface)],
)


@router.post(
    "/contracts",
    response_model=ContractDetailResponse,
    dependencies=[Depends(require_warfare_preview_write)],
)
async def create_contract(
    req: ContractCreateRequest,
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_session),
):
    """Create a mercenary contract. Escrow is deducted from your balance."""
    try:
        lock_keys = [agent_lock_key(agent.id)]
        if req.target_building_id is not None:
            lock_keys.append(building_lock_key(req.target_building_id))
        async with acquire_entity_locks(lock_keys):
            created = await warfare_svc.create_contract(
                session,
                employer_agent_id=agent.id,
                mission_type=req.mission_type,
                target_region_id=req.target_region_id,
                reward_per_agent=req.reward_per_agent,
                max_agents=req.max_agents,
                target_building_id=req.target_building_id,
                target_transport_id=req.target_transport_id,
                mission_duration_seconds=req.mission_duration_seconds,
                expires_in_seconds=req.expires_in_seconds,
            )
            result = await warfare_svc.get_contract(session, created["contract_id"])
            await session.commit()
            return result
    except ValueError as e:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(e)) from None


@router.get("/contracts", response_model=ContractListResponse)
async def list_contracts(
    region_id: int | None = Query(None),
    status: str | None = Query(None),
    mission_type: str | None = Query(None),
    limit: int = Query(50, le=100),
    session: AsyncSession = Depends(get_session),
):
    """List mercenary contracts with optional filters."""
    try:
        contracts = await warfare_svc.list_contracts(
            session,
            region_id=region_id,
            status=status,
            mission_type=mission_type,
            limit=limit,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    return {"contracts": contracts}


@router.get("/contracts/{contract_id}", response_model=ContractDetailResponse)
async def get_contract(
    contract_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Get contract details."""
    result = await warfare_svc.get_contract(session, contract_id)
    if not result:
        raise HTTPException(status_code=404, detail="Contract not found")
    return result


@router.post(
    "/contracts/{contract_id}/enlist",
    response_model=SuccessResponse,
    dependencies=[Depends(require_warfare_preview_write)],
)
async def enlist_in_contract(
    contract_id: int,
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_session),
):
    """Enlist as a mercenary in a contract."""
    try:
        async with acquire_entity_locks([agent_lock_key(agent.id), contract_lock_key(contract_id)]):
            result = await warfare_svc.enlist_in_contract(session, agent.id, contract_id)
            await session.commit()
            return {"message": f"Enlisted as {result['role']} ({result['enlisted_count']}/{result['max_agents']})"}
    except ValueError as e:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(e)) from None


@router.post(
    "/contracts/{contract_id}/activate",
    response_model=SuccessResponse,
    dependencies=[Depends(require_warfare_preview_write)],
)
async def activate_contract(
    contract_id: int,
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_session),
):
    """Activate a contract (employer only). Transitions OPEN → ACTIVE."""
    # Verify ownership
    contract = await warfare_svc.get_contract(session, contract_id)
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")
    if contract["employer_agent_id"] != agent.id:
        raise HTTPException(status_code=403, detail="Only the employer can activate")
    try:
        async with acquire_entity_locks([agent_lock_key(agent.id), contract_lock_key(contract_id)]):
            result = await warfare_svc.activate_contract(session, contract_id)
            await session.commit()
            return {"message": f"Contract activated with {result['active_agents']} agents"}
    except ValueError as e:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(e)) from None


@router.post(
    "/contracts/{contract_id}/cancel",
    response_model=SuccessResponse,
    dependencies=[Depends(require_warfare_preview_write)],
)
async def cancel_contract(
    contract_id: int,
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_session),
):
    """Cancel a contract. Employer gets refund minus cancellation fee."""
    try:
        async with acquire_entity_locks([agent_lock_key(agent.id), contract_lock_key(contract_id)]):
            result = await warfare_svc.cancel_contract(session, agent.id, contract_id)
            await session.commit()
            return {"message": f"Contract cancelled. Refund: {result['refund']}, fee: {result['fee']}"}
    except ValueError as e:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(e)) from None


@router.post(
    "/contracts/{contract_id}/execute",
    response_model=ContractExecutionResponse,
    dependencies=[Depends(require_warfare_preview_write)],
)
async def execute_contract(
    contract_id: int,
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_session),
):
    """Execute an active contract's mission (employer only)."""
    contract = await warfare_svc.get_contract(session, contract_id)
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")
    if contract["employer_agent_id"] != agent.id:
        raise HTTPException(status_code=403, detail="Only the employer can execute")

    try:
        lock_keys = [agent_lock_key(agent.id), contract_lock_key(contract_id)]
        if contract.get("target_building_id") is not None:
            lock_keys.append(building_lock_key(contract["target_building_id"]))
        async with acquire_entity_locks(lock_keys):
            mission_type = contract["mission_type"]
            if mission_type == "sabotage_building":
                result = await warfare_svc.execute_sabotage(session, contract_id)
            elif mission_type == "raid_transport":
                result = await warfare_svc.execute_transport_raid(session, contract_id)
            else:
                raise HTTPException(status_code=400, detail=f"Cannot execute {mission_type} contracts")
            await session.commit()
            return result
    except ValueError as e:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(e)) from None


@router.post(
    "/garrison/{building_id}",
    response_model=GarrisonResponse,
    dependencies=[Depends(require_warfare_preview_write)],
)
async def garrison_building(
    building_id: int,
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_session),
):
    """Assign yourself to garrison (defend) a building."""
    try:
        async with acquire_entity_locks([agent_lock_key(agent.id), building_lock_key(building_id)]):
            result = await warfare_svc.garrison_building(session, agent.id, building_id)
            await session.commit()
            return result
    except ValueError as e:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(e)) from None


@router.delete(
    "/garrison/{building_id}",
    response_model=SuccessResponse,
    dependencies=[Depends(require_warfare_preview_write)],
)
async def ungarrison_building(
    building_id: int,
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_session),
):
    """Remove yourself from a building's garrison."""
    try:
        async with acquire_entity_locks([agent_lock_key(agent.id), building_lock_key(building_id)]):
            await warfare_svc.ungarrison_building(session, agent.id, building_id)
            await session.commit()
            return {"message": "Ungarrisoned from building"}
    except ValueError as e:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(e)) from None


@router.post(
    "/repair/{building_id}",
    response_model=RepairResponse,
    dependencies=[Depends(require_warfare_preview_write)],
)
async def repair_building(
    building_id: int,
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_session),
):
    """Repair a damaged building using BLD resources."""
    try:
        async with acquire_entity_locks([agent_lock_key(agent.id), building_lock_key(building_id)]):
            result = await warfare_svc.repair_building(session, agent.id, building_id)
            await session.commit()
            return result
    except ValueError as e:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(e)) from None


@router.get("/region/{region_id}/threats", response_model=RegionThreatResponse)
async def get_region_threats(
    region_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Get active warfare threats in a region."""
    return await warfare_svc.get_region_threats(session, region_id)
