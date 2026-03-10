"""Admin-only preview control-plane endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from agentropolis.api.preview_guard import (
    ERROR_CODE_HEADER,
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


def _request_context(request: Request) -> tuple[str | None, str | None]:
    request_id = getattr(request.state, "request_id", None)
    client_fingerprint = getattr(request.state, "client_fingerprint", None)
    return request_id, client_fingerprint


def _control_plane_error(
    *,
    status_code: int,
    detail: str,
    error_code: str,
) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail=detail,
        headers={ERROR_CODE_HEADER: error_code},
    )


@router.get("", response_model=PreviewControlPlaneResponse)
async def get_control_plane_state(
    _admin_actor: str = Depends(require_control_plane_admin),
):
    """Return the effective preview control-plane policy."""
    return get_control_plane_admin_snapshot()


@router.put("", response_model=PreviewControlPlaneResponse)
async def update_control_plane_state(
    request: Request,
    req: PreviewControlPlaneUpdateRequest,
    admin_actor: str = Depends(require_control_plane_admin),
):
    """Apply process-local runtime overrides for preview policy."""
    request_id, client_fingerprint = _request_context(request)
    return update_preview_guard_state(
        surface_enabled=req.surface_enabled,
        writes_enabled=req.writes_enabled,
        warfare_mutations_enabled=req.warfare_mutations_enabled,
        degraded_mode=req.degraded_mode,
        audit_actor=admin_actor,
        request_id=request_id,
        client_fingerprint=client_fingerprint,
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
    request: Request,
    agent_id: int,
    req: PreviewAgentPolicyRequest,
    admin_actor: str = Depends(require_control_plane_admin),
):
    """Create or replace a process-local per-agent preview policy."""
    try:
        request_id, client_fingerprint = _request_context(request)
        return upsert_agent_preview_policy(
            agent_id,
            allowed_families=req.allowed_families,
            family_budgets=req.family_budgets,
            audit_actor=admin_actor,
            request_id=request_id,
            client_fingerprint=client_fingerprint,
            reason_code=req.reason_code,
            note=req.note,
        )
    except ValueError as exc:
        raise _control_plane_error(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
            error_code="control_plane_policy_invalid",
        ) from None


@router.post("/agents/{agent_id}/refill-budget", response_model=PreviewAgentPolicyResponse)
async def refill_agent_budget(
    request: Request,
    agent_id: int,
    req: PreviewAgentBudgetRefillRequest,
    admin_actor: str = Depends(require_control_plane_admin),
):
    """Increment process-local per-agent preview family budgets."""
    try:
        request_id, client_fingerprint = _request_context(request)
        return refill_agent_preview_budget(
            agent_id,
            increments=req.increments,
            audit_actor=admin_actor,
            request_id=request_id,
            client_fingerprint=client_fingerprint,
            reason_code=req.reason_code,
            note=req.note,
        )
    except ValueError as exc:
        raise _control_plane_error(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
            error_code="control_plane_budget_refill_invalid",
        ) from None


@router.delete("/agents/{agent_id}/policy", response_model=SuccessResponse)
async def delete_agent_policy(
    request: Request,
    agent_id: int,
    reason_code: str | None = Query(default=None, min_length=2, max_length=64),
    note: str | None = Query(default=None, min_length=2, max_length=280),
    admin_actor: str = Depends(require_control_plane_admin),
):
    """Remove a process-local per-agent preview policy."""
    request_id, client_fingerprint = _request_context(request)
    existed = clear_agent_preview_policy(
        agent_id,
        audit_actor=admin_actor,
        request_id=request_id,
        client_fingerprint=client_fingerprint,
        reason_code=reason_code,
        note=note,
    )
    if not existed:
        raise _control_plane_error(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Preview agent policy not found.",
            error_code="control_plane_policy_not_found",
        )
    return {"message": f"Preview agent policy cleared for agent {agent_id}."}


@router.get("/audit", response_model=ControlPlaneAuditResponse)
async def get_control_plane_audit(
    limit: int = Query(default=20, ge=0, le=200),
    action: str | None = Query(default=None),
    target_agent_id: int | None = Query(default=None),
    reason_code: str | None = Query(default=None),
    request_id: str | None = Query(default=None),
    _admin_actor: str = Depends(require_control_plane_admin),
):
    """List recent admin actions against the process-local preview policy."""
    return {
        "entries": list_control_plane_audit(
            limit=limit,
            action=action,
            target_agent_id=target_agent_id,
            reason_code=reason_code,
            request_id=request_id,
        )
    }


@router.post("/reset-rate-limits", response_model=SuccessResponse)
async def reset_control_plane_rate_limits(
    request: Request,
    req: ControlPlaneActionRequest,
    admin_actor: str = Depends(require_control_plane_admin),
):
    """Clear process-local preview runtime counters and overrides."""
    request_id, client_fingerprint = _request_context(request)
    reset_preview_guard_runtime(
        audit_actor=admin_actor,
        request_id=request_id,
        client_fingerprint=client_fingerprint,
        reason_code=req.reason_code,
        note=req.note,
    )
    return {"message": "Preview control-plane runtime state reset."}
