"""Production REST API endpoints.

Dependencies: services/production.py
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from agentropolis.api.auth import get_current_company
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

router = APIRouter(prefix="/production", tags=["production"])


@router.get("/buildings", response_model=list[BuildingInfo])
async def get_buildings(
    company: Company = Depends(get_current_company),
    session: AsyncSession = Depends(get_session),
):
    """Get all your buildings and their status."""
    raise NotImplementedError("Issue #9: Implement production API endpoints")


@router.get("/recipes", response_model=list[RecipeInfo])
async def get_recipes(
    building_type: str | None = None,
    session: AsyncSession = Depends(get_session),
):
    """Get available recipes, optionally filtered by building type."""
    raise NotImplementedError("Issue #9: Implement production API endpoints")


@router.get("/building-types", response_model=list[BuildingTypeInfo])
async def get_building_types(session: AsyncSession = Depends(get_session)):
    """Get all building types and their costs."""
    raise NotImplementedError("Issue #9: Implement production API endpoints")


@router.post("/start", response_model=SuccessResponse)
async def start_production(
    req: StartProductionRequest,
    company: Company = Depends(get_current_company),
    session: AsyncSession = Depends(get_session),
):
    """Start production on a building with a recipe."""
    raise NotImplementedError("Issue #9: Implement production API endpoints")


@router.post("/stop", response_model=SuccessResponse)
async def stop_production(
    building_id: int,
    company: Company = Depends(get_current_company),
    session: AsyncSession = Depends(get_session),
):
    """Stop production on a building."""
    raise NotImplementedError("Issue #9: Implement production API endpoints")


@router.post("/build", response_model=SuccessResponse)
async def build_building(
    req: BuildBuildingRequest,
    company: Company = Depends(get_current_company),
    session: AsyncSession = Depends(get_session),
):
    """Construct a new building."""
    raise NotImplementedError("Issue #9: Implement production API endpoints")
