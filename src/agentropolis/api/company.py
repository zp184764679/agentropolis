"""Company REST API endpoints.

Dependencies: services/company_svc.py
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from agentropolis.api.auth import get_current_company
from agentropolis.api.schemas import (
    CompanyStatus,
    RegisterRequest,
    RegisterResponse,
    WorkerInfo,
)
from agentropolis.database import get_session
from agentropolis.models import Company

router = APIRouter(prefix="/company", tags=["company"])


@router.post("/register", response_model=RegisterResponse)
async def register_company(
    req: RegisterRequest, session: AsyncSession = Depends(get_session)
):
    """Register a new company and get your API key."""
    raise NotImplementedError("Issue #11: Implement company API endpoints")


@router.get("/status", response_model=CompanyStatus)
async def get_status(
    company: Company = Depends(get_current_company),
    session: AsyncSession = Depends(get_session),
):
    """Get your company's current status."""
    raise NotImplementedError("Issue #11: Implement company API endpoints")


@router.get("/workers", response_model=WorkerInfo)
async def get_workers(
    company: Company = Depends(get_current_company),
    session: AsyncSession = Depends(get_session),
):
    """Get your workforce details."""
    raise NotImplementedError("Issue #11: Implement company API endpoints")
