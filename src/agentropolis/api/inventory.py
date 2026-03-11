"""Inventory REST API endpoints.

Dependencies: services/inventory_svc.py
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentropolis.api.auth import get_current_agent_company
from agentropolis.api.preview_guard import ERROR_CODE_HEADER, make_agent_preview_access_guard
from agentropolis.api.schemas import InventoryItem, InventoryResponse, ResourceInfo
from agentropolis.database import get_session
from agentropolis.models import Company, Resource
from agentropolis.services import inventory_svc

router = APIRouter(prefix="/inventory", tags=["inventory"])
inventory_access_guard = make_agent_preview_access_guard("company_inventory")


@router.get("", response_model=InventoryResponse)
async def get_inventory(
    _guard: None = Depends(inventory_access_guard),
    company: Company = Depends(get_current_agent_company),
    session: AsyncSession = Depends(get_session),
):
    """Get your complete inventory."""
    items = await inventory_svc.get_inventory(session, company.id)
    return {
        "items": [
            {
                "ticker": item["ticker"],
                "name": item["name"],
                "quantity": item["quantity"],
                "reserved": item["reserved"],
                "available": item["available"],
            }
            for item in items
        ],
        "total_value": sum(item["available"] * item["base_price"] for item in items),
    }


@router.get("/{ticker}", response_model=InventoryItem)
async def get_resource_detail(
    ticker: str,
    _guard: None = Depends(inventory_access_guard),
    company: Company = Depends(get_current_agent_company),
    session: AsyncSession = Depends(get_session),
):
    """Get detail for a specific resource in your inventory."""
    try:
        detail = await inventory_svc.get_resource_quantity(session, company.id, ticker)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
            headers={ERROR_CODE_HEADER: "inventory_resource_not_found"},
        ) from None

    return {
        "ticker": detail["ticker"],
        "name": detail["name"],
        "quantity": detail["quantity"],
        "reserved": detail["reserved"],
        "available": detail["available"],
    }


@router.get("/info/{ticker}", response_model=ResourceInfo)
async def get_resource_info(ticker: str, session: AsyncSession = Depends(get_session)):
    """Get static info about a resource (no auth required)."""
    resource = (
        await session.execute(select(Resource).where(Resource.ticker == ticker))
    ).scalar_one_or_none()
    if resource is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown resource ticker: {ticker}",
            headers={ERROR_CODE_HEADER: "inventory_resource_not_found"},
        )
    return {
        "ticker": resource.ticker,
        "name": resource.name,
        "category": resource.category.value,
        "base_price": int(resource.base_price),
        "description": resource.description or "",
    }
