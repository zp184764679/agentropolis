"""Production REST API endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from agentropolis.api.auth import get_current_company
from agentropolis.api.preview_guard import (
    ERROR_CODE_HEADER,
    make_company_preview_write_guard,
)
from agentropolis.api.schemas import (
    BuildBuildingRequest,
    BuildingInfo,
    BuildingTypeInfo,
    RecipeInfo,
    StartProductionRequest,
    SuccessResponse,
)
from agentropolis.database import get_session
from agentropolis.models import Company
from agentropolis.services.concurrency import acquire_entity_locks, company_lock_key
from agentropolis.services.production import (
    build_building as build_building_svc,
    estimate_build_building_cost as estimate_build_building_cost_svc,
    get_building_types as get_building_types_svc,
    get_company_buildings,
    get_recipes as get_recipes_svc,
    start_production as start_production_svc,
    stop_production as stop_production_svc,
)

router = APIRouter(prefix="/production", tags=["production"])


async def _build_building_spend_resolver(request, session, _company) -> int:
    payload = await request.json()
    return await estimate_build_building_cost_svc(session, payload["building_type"])


production_build_guard = make_company_preview_write_guard(
    "company_production",
    operation="build_building",
    spend_resolver=_build_building_spend_resolver,
)
production_start_guard = make_company_preview_write_guard(
    "company_production",
    operation="start_production",
)
production_stop_guard = make_company_preview_write_guard(
    "company_production",
    operation="stop_production",
)


@router.get("/buildings", response_model=list[BuildingInfo])
async def get_buildings(
    company: Company = Depends(get_current_company),
    session: AsyncSession = Depends(get_session),
):
    """Get all your buildings and their status."""
    return await get_company_buildings(session, company.id)


@router.get("/recipes", response_model=list[RecipeInfo])
async def get_recipes(
    building_type: str | None = None,
    session: AsyncSession = Depends(get_session),
):
    """Get available recipes, optionally filtered by building type."""
    try:
        return await get_recipes_svc(session, building_type)
    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
            headers={ERROR_CODE_HEADER: "production_recipe_not_found"},
        ) from None


@router.get("/building-types", response_model=list[BuildingTypeInfo])
async def get_building_types(session: AsyncSession = Depends(get_session)):
    """Get all building types and their costs."""
    return await get_building_types_svc(session)


@router.post(
    "/start",
    response_model=SuccessResponse,
    dependencies=[Depends(production_start_guard)],
)
async def start_production(
    req: StartProductionRequest,
    company: Company = Depends(get_current_company),
    session: AsyncSession = Depends(get_session),
):
    """Start production on a building with a recipe."""
    try:
        async with acquire_entity_locks([company_lock_key(company.id)]):
            result = await start_production_svc(session, company.id, req.building_id, req.recipe_id)
            await session.commit()
            return {
                "message": (
                    f"Started {result['recipe']} on building {result['building_id']} "
                    f"(eta {result['eta_ticks']} ticks)."
                )
            }
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=400,
            detail=str(exc),
            headers={ERROR_CODE_HEADER: "production_start_invalid"},
        ) from None


@router.post(
    "/stop",
    response_model=SuccessResponse,
    dependencies=[Depends(production_stop_guard)],
)
async def stop_production(
    building_id: int,
    company: Company = Depends(get_current_company),
    session: AsyncSession = Depends(get_session),
):
    """Stop production on a building."""
    async with acquire_entity_locks([company_lock_key(company.id)]):
        stopped = await stop_production_svc(session, company.id, building_id)
        await session.commit()
        if not stopped:
            return {"message": f"Building {building_id} was already idle."}
        return {"message": f"Stopped production on building {building_id}."}


@router.post(
    "/build",
    response_model=SuccessResponse,
    dependencies=[Depends(production_build_guard)],
)
async def build_building(
    req: BuildBuildingRequest,
    company: Company = Depends(get_current_company),
    session: AsyncSession = Depends(get_session),
):
    """Construct a new building."""
    try:
        async with acquire_entity_locks([company_lock_key(company.id)]):
            result = await build_building_svc(session, company.id, req.building_type)
            await session.commit()
            return {
                "message": (
                    f"Constructed {result['building_type']} as building {result['building_id']}."
                )
            }
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=400,
            detail=str(exc),
            headers={ERROR_CODE_HEADER: "production_build_invalid"},
        ) from None
