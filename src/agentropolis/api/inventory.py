"""Inventory REST API endpoints.

Dependencies: services/inventory_svc.py
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from agentropolis.api.auth import get_current_company
from agentropolis.api.schemas import InventoryItem, InventoryResponse, ResourceInfo
from agentropolis.database import get_session
from agentropolis.models import Company

router = APIRouter(prefix="/inventory", tags=["inventory"])


@router.get("", response_model=InventoryResponse)
async def get_inventory(
    company: Company = Depends(get_current_company),
    session: AsyncSession = Depends(get_session),
):
    """Get your complete inventory."""
    raise NotImplementedError("Issue #10: Implement inventory API endpoints")


@router.get("/{ticker}", response_model=InventoryItem)
async def get_resource_detail(
    ticker: str,
    company: Company = Depends(get_current_company),
    session: AsyncSession = Depends(get_session),
):
    """Get detail for a specific resource in your inventory."""
    raise NotImplementedError("Issue #10: Implement inventory API endpoints")


@router.get("/info/{ticker}", response_model=ResourceInfo)
async def get_resource_info(ticker: str, session: AsyncSession = Depends(get_session)):
    """Get static info about a resource (no auth required)."""
    raise NotImplementedError("Issue #10: Implement inventory API endpoints")
