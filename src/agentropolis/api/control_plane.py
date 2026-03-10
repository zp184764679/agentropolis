"""Admin-only preview control-plane endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query

from agentropolis.api.preview_guard import (
    clear_agent_preview_policy,
    get_control_plane_admin_snapshot,
    list_control_plane_audit,
    refill_agent_preview_budget,
    require_control_plane_admin,
    reset_preview_guard_runtime,
    upsert_agent_preview_policy,
    update_preview_guard_state,
)
from agentropolis.api.schemas import (
    ControlPlaneActionRequest,
    ControlPlaneAuditResponse,
    PreviewAgentBudgetRefillRequest,
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
        reason_code=req.reason_code,
        note=req.note,
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
            reason_code=req.reason_code,
            note=req.note,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None


@router.post("/agents/{agent_id}/refill-budget", response_model=PreviewAgentPolicyResponse)
async def refill_agent_budget(
    agent_id: int,
    req: PreviewAgentBudgetRefillRequest,
    admin_actor: str = Depends(require_control_plane_admin),
):
    """Increment process-local per-agent preview family budgets."""
    try:
        return refill_agent_preview_budget(
            agent_id,
            increments=req.increments,
            audit_actor=admin_actor,
            reason_code=req.reason_code,
            note=req.note,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None


@router.delete("/agents/{agent_id}/policy", response_model=SuccessResponse)
async def delete_agent_policy(
    agent_id: int,
    reason_code: str | None = Query(default=None, min_length=2, max_length=64),
    note: str | None = Query(default=None, min_length=2, max_length=280),
    admin_actor: str = Depends(require_control_plane_admin),
):
    """Remove a process-local per-agent preview policy."""
    existed = clear_agent_preview_policy(
        agent_id,
        audit_actor=admin_actor,
        reason_code=reason_code,
        note=note,
    )
    if not existed:
        raise HTTPException(status_code=404, detail="Preview agent policy not found.")
    return {"message": f"Preview agent policy cleared for agent {agent_id}."}


@router.get("/audit", response_model=ControlPlaneAuditResponse)
async def get_control_plane_audit(
    limit: int = Query(default=20, ge=0, le=200),
    action: str | None = Query(default=None),
    target_agent_id: int | None = Query(default=None),
    reason_code: str | None = Query(default=None),
    _admin_actor: str = Depends(require_control_plane_admin),
):
    """List recent admin actions against the process-local preview policy."""
    return {
        "entries": list_control_plane_audit(
            limit=limit,
            action=action,
            target_agent_id=target_agent_id,
            reason_code=reason_code,
        )
    }


@router.post("/reset-rate-limits", response_model=SuccessResponse)
async def reset_control_plane_rate_limits(
    req: ControlPlaneActionRequest,
    admin_actor: str = Depends(require_control_plane_admin),
):
    """Clear process-local preview runtime counters and overrides."""
    reset_preview_guard_runtime(
        audit_actor=admin_actor,
        reason_code=req.reason_code,
        note=req.note,
    )
    return {"message": "Preview control-plane runtime state reset."}
