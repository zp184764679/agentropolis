"""Derived alerts endpoint for local-preview operations."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from agentropolis.api.preview_guard import get_preview_guard_state
from agentropolis.database import get_session
from agentropolis.runtime_meta import build_runtime_metadata
from agentropolis.services.alerts_svc import build_alert_snapshot

router = APIRouter(prefix="/meta/alerts", tags=["alerts"])


@router.get("")
async def read_alerts(session: AsyncSession = Depends(get_session)):
    runtime_meta = build_runtime_metadata(
        preview_guard_state=await get_preview_guard_state(session)
    )
    return await build_alert_snapshot(session, runtime_meta)
