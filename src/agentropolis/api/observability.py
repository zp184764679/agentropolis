"""Local-preview observability endpoint."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from agentropolis.database import get_session
from agentropolis.services.observability_svc import build_observability_snapshot

router = APIRouter(prefix="/meta/observability", tags=["observability"])


@router.get("")
async def read_observability(session: AsyncSession = Depends(get_session)):
    return await build_observability_snapshot(session)
