"""Local-preview rollout readiness endpoint."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from agentropolis.api.preview_guard import get_preview_guard_state
from agentropolis.database import get_session
from agentropolis.runtime_meta import build_runtime_metadata
from agentropolis.services.rollout_readiness_svc import build_rollout_readiness_snapshot

router = APIRouter(prefix="/meta/rollout-readiness", tags=["rollout-readiness"])


@router.get("")
async def read_rollout_readiness(session: AsyncSession = Depends(get_session)):
    meta = build_runtime_metadata(
        preview_guard_state=await get_preview_guard_state(session)
    )
    return await build_rollout_readiness_snapshot(session, meta)
