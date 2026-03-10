"""Company REST API endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from agentropolis.api.auth import get_current_agent, get_current_company
from agentropolis.api.preview_guard import ERROR_CODE_HEADER
from agentropolis.api.schemas import (
    CompanyStatus,
    RegisterRequest,
    RegisterResponse,
    WorkerInfo,
)
from agentropolis.database import get_session
from agentropolis.models import Agent, Company
from agentropolis.services.company_svc import (
    get_company_status,
    get_company_workers,
    register_company as register_company_svc,
)

router = APIRouter(prefix="/company", tags=["company"])


@router.post("/register", response_model=RegisterResponse)
async def register_company(
    req: RegisterRequest,
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_session),
):
    """Register a new company and get your API key."""
    try:
        result = await register_company_svc(
            session,
            req.company_name,
            founder_agent_id=agent.id,
        )
        await session.commit()
        return result
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=400,
            detail=str(exc),
            headers={ERROR_CODE_HEADER: "company_register_invalid"},
        ) from None


@router.get("/status", response_model=CompanyStatus)
async def get_status(
    company: Company = Depends(get_current_company),
    session: AsyncSession = Depends(get_session),
):
    """Get your company's current status."""
    try:
        return await get_company_status(session, company.id)
    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
            headers={ERROR_CODE_HEADER: "company_not_found"},
        ) from None


@router.get("/workers", response_model=WorkerInfo)
async def get_workers(
    company: Company = Depends(get_current_company),
    session: AsyncSession = Depends(get_session),
):
    """Get your workforce details."""
    try:
        return await get_company_workers(session, company.id)
    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
            headers={ERROR_CODE_HEADER: "company_not_found"},
        ) from None
