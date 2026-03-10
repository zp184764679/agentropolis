"""Admin-only preview control-plane endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query

from agentropolis.api.preview_guard import (
    clear_agent_preview_policy,
    get_control_plane_admin_snapshot,
    list_control_plane_audit,
    require_control_plane_admin,
    reset_preview_guard_runtime,
    upsert_agent_preview_policy,
    update_preview_guard_state,
)
from agentropolis.api.schemas import (
    ControlPlaneAuditResponse,
    PreviewAgentPolicyListResponse,
    PreviewAgentPolicyRequest,
    PreviewAgentPolicyResponse,
    PreviewControlPlaneResponse,
    PreviewControlPlaneUpdateRequest,
    SuccessResponse,
)

router = APIRouter(prefix="/meta/control-plane", tags=["control-plane"])


@router.get("", response_model=PreviewControlPlaneResponse)
async def get_control_plane_state(
    _admin_actor: str = Depends(require_control_plane_admin),
):
    """Return the effective preview control-plane policy."""
    return get_control_plane_admin_snapshot()


@router.put("", response_model=PreviewControlPlaneResponse)
async def update_control_plane_state(
    req: PreviewControlPlaneUpdateRequest,
    admin_actor: str = Depends(require_control_plane_admin),
):
    """Apply process-local runtime overrides for preview policy."""
    return update_preview_guard_state(
        surface_enabled=req.surface_enabled,
        writes_enabled=req.writes_enabled,
        warfare_mutations_enabled=req.warfare_mutations_enabled,
        degraded_mode=req.degraded_mode,
        audit_actor=admin_actor,
    )


@router.get("/agents", response_model=PreviewAgentPolicyListResponse)
async def list_agent_policies(
    _admin_actor: str = Depends(require_control_plane_admin),
):
    """List all process-local per-agent preview policies."""
    snapshot = get_control_plane_admin_snapshot(audit_limit=0)
    return {"policies": snapshot["agent_policies"]}


@router.put("/agents/{agent_id}/policy", response_model=PreviewAgentPolicyResponse)
async def upsert_agent_policy(
    agent_id: int,
    req: PreviewAgentPolicyRequest,
    admin_actor: str = Depends(require_control_plane_admin),
):
    """Create or replace a process-local per-agent preview policy."""
    try:
        return upsert_agent_preview_policy(
            agent_id,
            allowed_families=req.allowed_families,
            family_budgets=req.family_budgets,
            audit_actor=admin_actor,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None


@router.delete("/agents/{agent_id}/policy", response_model=SuccessResponse)
async def delete_agent_policy(
    agent_id: int,
    admin_actor: str = Depends(require_control_plane_admin),
):
    """Remove a process-local per-agent preview policy."""
    existed = clear_agent_preview_policy(agent_id, audit_actor=admin_actor)
    if not existed:
        raise HTTPException(status_code=404, detail="Preview agent policy not found.")
    return {"message": f"Preview agent policy cleared for agent {agent_id}."}


@router.get("/audit", response_model=ControlPlaneAuditResponse)
async def get_control_plane_audit(
    limit: int = Query(default=20, ge=0, le=200),
    _admin_actor: str = Depends(require_control_plane_admin),
):
    """List recent admin actions against the process-local preview policy."""
    return {"entries": list_control_plane_audit(limit=limit)}


@router.post("/reset-rate-limits", response_model=SuccessResponse)
async def reset_control_plane_rate_limits(
    admin_actor: str = Depends(require_control_plane_admin),
):
    """Clear process-local preview runtime counters and overrides."""
    reset_preview_guard_runtime(audit_actor=admin_actor)
    return {"message": "Preview control-plane runtime state reset."}
