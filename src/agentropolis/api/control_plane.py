"""Admin-only preview control-plane endpoints."""

from fastapi import APIRouter, Depends

from agentropolis.api.preview_guard import (
    get_preview_guard_state,
    require_control_plane_admin,
    reset_preview_guard_state,
    update_preview_guard_state,
)
from agentropolis.api.schemas import (
    PreviewControlPlaneResponse,
    PreviewControlPlaneUpdateRequest,
    SuccessResponse,
)

router = APIRouter(
    prefix="/meta/control-plane",
    tags=["control-plane"],
    dependencies=[Depends(require_control_plane_admin)],
)


@router.get("", response_model=PreviewControlPlaneResponse)
async def get_control_plane_state():
    """Return the effective preview control-plane policy."""
    return get_preview_guard_state()


@router.put("", response_model=PreviewControlPlaneResponse)
async def update_control_plane_state(req: PreviewControlPlaneUpdateRequest):
    """Apply process-local runtime overrides for preview policy."""
    return update_preview_guard_state(
        surface_enabled=req.surface_enabled,
        writes_enabled=req.writes_enabled,
        warfare_mutations_enabled=req.warfare_mutations_enabled,
        degraded_mode=req.degraded_mode,
    )


@router.post("/reset-rate-limits", response_model=SuccessResponse)
async def reset_control_plane_rate_limits():
    """Clear process-local preview guard state and counters."""
    reset_preview_guard_state()
    return {"message": "Preview control-plane rate limits and overrides reset."}
