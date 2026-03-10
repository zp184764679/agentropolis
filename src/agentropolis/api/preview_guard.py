"""Preview/control-plane guardrails with DB-backed policy state.

Short-lived mutation windows remain process-local best effort.
Durable policy, budgets, and audit trail are stored in the database.
"""

from __future__ import annotations

from collections import defaultdict, deque
from datetime import UTC, datetime
import hashlib
from threading import Lock
from time import monotonic
from typing import Any

from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import APIKeyHeader
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agentropolis.api.auth import get_current_agent
from agentropolis.config import settings
from agentropolis.database import get_session
from agentropolis.middleware import REQUEST_ID_HEADER
from agentropolis.models import (
    ControlPlaneAuditLog,
    PreviewAgentPolicy,
    PreviewControlPlaneState,
)

ERROR_CODE_HEADER = "X-Agentropolis-Error-Code"
ERROR_CODE_CATALOG = {
    "request_validation_failed": "Request payload, path params, or query params failed validation.",
    "preview_surface_disabled": "Global preview surface kill switch is active.",
    "preview_writes_disabled": "Preview writes are disabled by runtime policy.",
    "preview_warfare_mutations_disabled": "Warfare preview mutations are disabled.",
    "preview_{family}_degraded_mode_blocked": "Preview mutations for this route family are blocked in degraded mode.",
    "preview_{family}_rate_limited": "Preview mutation quota exceeded for this route family.",
    "preview_registration_rate_limited": "Preview registration quota exceeded for this client fingerprint.",
    "preview_mutation_rate_limited": "Generic preview mutation quota exceeded.",
    "preview_{family}_access_denied": "Authenticated preview access is not allowed for this route family.",
    "preview_{family}_budget_exhausted": "Configured preview mutation budget for this route family is exhausted.",
    "control_plane_admin_unconfigured": "Control-plane admin token is not configured.",
    "control_plane_admin_invalid": "Control-plane admin token is invalid.",
    "control_plane_policy_invalid": "Submitted control-plane agent policy payload is invalid.",
    "control_plane_budget_refill_invalid": "Submitted budget refill payload is invalid.",
    "control_plane_policy_not_found": "Requested preview agent policy does not exist.",
    "not_implemented": "Legacy scaffold handler is mounted but not implemented yet.",
}

admin_token_header = APIKeyHeader(name="X-Control-Plane-Token", auto_error=False)

_mutation_windows: dict[str, deque[float]] = defaultdict(deque)
_mutation_lock = Lock()

_FAMILY_LIMIT_ATTRS = {
    "agent_self": "PREVIEW_AGENT_SELF_MUTATIONS_PER_WINDOW",
    "world": "PREVIEW_WORLD_MUTATIONS_PER_WINDOW",
    "transport": "PREVIEW_TRANSPORT_MUTATIONS_PER_WINDOW",
    "social": "PREVIEW_SOCIAL_MUTATIONS_PER_WINDOW",
    "strategy": "PREVIEW_STRATEGY_MUTATIONS_PER_WINDOW",
    "warfare": "PREVIEW_WARFARE_MUTATIONS_PER_WINDOW",
}


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _isoformat(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.isoformat()


def _record_window_event(
    key: str,
    *,
    limit: int,
    window_seconds: int,
    detail: str,
    error_code: str,
) -> None:
    if limit <= 0:
        return

    now = monotonic()
    cutoff = now - window_seconds
    with _mutation_lock:
        bucket = _mutation_windows[key]
        while bucket and bucket[0] <= cutoff:
            bucket.popleft()

        if len(bucket) >= limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=detail,
                headers={
                    "Retry-After": str(window_seconds),
                    ERROR_CODE_HEADER: error_code,
                },
            )

        bucket.append(now)


def _client_fingerprint(request: Request) -> str:
    client = request.client
    if client is None:
        return "unknown"
    return f"{client.host}:{client.port}"


def _guard_exception(
    *,
    status_code: int,
    detail: str,
    error_code: str,
    headers: dict[str, str] | None = None,
) -> HTTPException:
    merged_headers = dict(headers or {})
    merged_headers[ERROR_CODE_HEADER] = error_code
    return HTTPException(
        status_code=status_code,
        detail=detail,
        headers=merged_headers,
    )


def _family_limit(family: str) -> int:
    attr = _FAMILY_LIMIT_ATTRS.get(family, "PREVIEW_AGENT_MUTATIONS_PER_WINDOW")
    return int(getattr(settings, attr))


def _validate_family(family: str) -> str:
    if family not in _FAMILY_LIMIT_ATTRS:
        raise ValueError(f"Unknown preview policy family: {family}")
    return family


def _normalize_allowed_families(families: list[str] | None) -> list[str] | None:
    if families is None:
        return None
    return sorted({_validate_family(family) for family in families})


def _normalize_family_budgets(family_budgets: dict[str, int] | None) -> dict[str, int]:
    if not family_budgets:
        return {}
    normalized: dict[str, int] = {}
    for family, budget in family_budgets.items():
        _validate_family(family)
        amount = int(budget)
        if amount < 0:
            raise ValueError(f"Preview budget for {family} must be >= 0")
        normalized[family] = amount
    return normalized


def _policy_value(override: bool | None, default: bool) -> bool:
    return default if override is None else bool(override)


def _serialize_agent_policy(policy: PreviewAgentPolicy) -> dict[str, Any]:
    updated_at = policy.__dict__.get("updated_at")
    return {
        "agent_id": policy.agent_id,
        "allowed_families": list(policy.allowed_families)
        if policy.allowed_families is not None
        else None,
        "family_budgets": dict(policy.family_budgets or {}),
        "updated_at": _isoformat(updated_at) or _utc_now().isoformat(),
    }


def _serialize_audit_entry(entry: ControlPlaneAuditLog) -> dict[str, Any]:
    occurred_at = entry.__dict__.get("occurred_at")
    return {
        "event_id": entry.id,
        "action": entry.action,
        "actor": entry.actor,
        "target_agent_id": entry.target_agent_id,
        "request_id": entry.request_id,
        "client_fingerprint": entry.client_fingerprint,
        "reason_code": entry.reason_code,
        "note": entry.note,
        "payload": dict(entry.payload or {}),
        "occurred_at": _isoformat(occurred_at) or _utc_now().isoformat(),
    }


async def _get_or_create_control_plane_state(
    session: AsyncSession,
) -> PreviewControlPlaneState:
    state = await session.get(PreviewControlPlaneState, 1)
    if state is None:
        state = PreviewControlPlaneState(id=1)
        session.add(state)
        await session.flush()
    return state


async def _get_agent_policy(
    session: AsyncSession,
    agent_id: int,
    *,
    for_update: bool = False,
) -> PreviewAgentPolicy | None:
    stmt = select(PreviewAgentPolicy).where(PreviewAgentPolicy.agent_id == agent_id)
    if for_update:
        stmt = stmt.with_for_update()
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def _record_admin_action(
    session: AsyncSession,
    action: str,
    *,
    actor: str,
    target_agent_id: int | None = None,
    request_id: str | None = None,
    client_fingerprint: str | None = None,
    reason_code: str | None = None,
    note: str | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    session.add(
        ControlPlaneAuditLog(
            action=action,
            actor=actor,
            target_agent_id=target_agent_id,
            request_id=request_id,
            client_fingerprint=client_fingerprint,
            reason_code=reason_code,
            note=note,
            payload=payload or {},
        )
    )
    await session.flush()


async def _get_effective_global_policy(session: AsyncSession) -> dict[str, bool]:
    state = await _get_or_create_control_plane_state(session)
    return {
        "surface_enabled": _policy_value(
            state.surface_enabled_override,
            settings.PREVIEW_SURFACE_ENABLED,
        ),
        "writes_enabled": _policy_value(
            state.writes_enabled_override,
            settings.PREVIEW_WRITES_ENABLED,
        ),
        "warfare_mutations_enabled": _policy_value(
            state.warfare_mutations_enabled_override,
            settings.WARFARE_MUTATIONS_ENABLED,
        ),
        "degraded_mode": _policy_value(
            state.degraded_mode_override,
            settings.PREVIEW_DEGRADED_MODE,
        ),
    }


async def _apply_agent_policy_gate(
    session: AsyncSession,
    *,
    agent_id: int,
    family: str,
    consume_budget: bool,
) -> None:
    policy = await _get_agent_policy(session, agent_id, for_update=consume_budget)
    if policy is None:
        return

    allowed_families = policy.allowed_families
    if allowed_families is not None and family not in allowed_families:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Preview {family} access is not allowed for agent {agent_id}.",
            headers={ERROR_CODE_HEADER: f"preview_{family}_access_denied"},
        )

    family_budgets = dict(policy.family_budgets or {})
    remaining = family_budgets.get(family)
    if remaining is None:
        return
    if int(remaining) <= 0:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Preview {family} budget exhausted for agent {agent_id}.",
            headers={ERROR_CODE_HEADER: f"preview_{family}_budget_exhausted"},
        )
    if consume_budget:
        family_budgets[family] = int(remaining) - 1
        policy.family_budgets = family_budgets
        await session.flush()


async def _require_preview_surface_enabled(session: AsyncSession) -> None:
    state = await _get_effective_global_policy(session)
    if not state["surface_enabled"]:
        raise _guard_exception(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Preview surface is disabled by runtime policy.",
            error_code="preview_surface_disabled",
        )


async def _require_preview_writes_enabled(session: AsyncSession) -> None:
    state = await _get_effective_global_policy(session)
    if not state["writes_enabled"]:
        raise _guard_exception(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Preview write operations are disabled by runtime policy.",
            error_code="preview_writes_disabled",
        )


async def _require_warfare_mutations_enabled(session: AsyncSession) -> None:
    state = await _get_effective_global_policy(session)
    if not state["warfare_mutations_enabled"]:
        raise _guard_exception(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Warfare preview mutations are disabled by runtime policy.",
            error_code="preview_warfare_mutations_disabled",
        )


async def _require_family_degraded_policy(
    session: AsyncSession,
    family: str,
    *,
    allow_in_degraded_mode: bool,
) -> None:
    state = await _get_effective_global_policy(session)
    if state["degraded_mode"] and not allow_in_degraded_mode:
        raise _guard_exception(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Preview {family} mutations are disabled in degraded mode.",
            error_code=f"preview_{family}_degraded_mode_blocked",
        )


def _record_agent_mutation(agent_id: Any, family: str) -> None:
    _record_window_event(
        f"preview-family:{family}:agent:{agent_id}",
        limit=_family_limit(family),
        window_seconds=settings.PREVIEW_MUTATION_WINDOW_SECONDS,
        detail=f"Preview {family} mutation rate limit exceeded.",
        error_code=f"preview_{family}_rate_limited",
    )


async def require_preview_surface(
    session: AsyncSession = Depends(get_session),
) -> None:
    """Block all mounted preview routes behind the global runtime switch."""
    await _require_preview_surface_enabled(session)


async def require_preview_registration_write(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> None:
    """Guard unauthenticated agent registration on the preview surface."""
    await _require_preview_surface_enabled(session)
    await _require_preview_writes_enabled(session)
    _record_window_event(
        f"preview-registration:{_client_fingerprint(request)}",
        limit=settings.PREVIEW_REGISTRATIONS_PER_WINDOW_PER_HOST,
        window_seconds=settings.PREVIEW_MUTATION_WINDOW_SECONDS,
        detail="Preview registration rate limit exceeded.",
        error_code="preview_registration_rate_limited",
    )


def make_agent_preview_access_guard(family: str):
    """Build a dependency that guards authenticated preview reads for one route family."""

    async def dependency(
        agent: Any = Depends(get_current_agent),
        session: AsyncSession = Depends(get_session),
    ) -> None:
        await _require_preview_surface_enabled(session)
        await _apply_agent_policy_gate(
            session,
            agent_id=agent.id,
            family=family,
            consume_budget=False,
        )

    return dependency


def make_agent_preview_write_guard(
    family: str,
    *,
    allow_in_degraded_mode: bool = False,
):
    """Build a dependency that guards preview mutations for one route family."""

    async def dependency(
        agent: Any = Depends(get_current_agent),
        session: AsyncSession = Depends(get_session),
    ) -> None:
        await _require_preview_surface_enabled(session)
        await _require_preview_writes_enabled(session)
        await _require_family_degraded_policy(
            session,
            family,
            allow_in_degraded_mode=allow_in_degraded_mode,
        )
        await _apply_agent_policy_gate(
            session,
            agent_id=agent.id,
            family=family,
            consume_budget=False,
        )
        _record_agent_mutation(agent.id, family)
        await _apply_agent_policy_gate(
            session,
            agent_id=agent.id,
            family=family,
            consume_budget=True,
        )

    return dependency


async def require_agent_preview_write(
    agent: Any = Depends(get_current_agent),
    session: AsyncSession = Depends(get_session),
) -> None:
    """Backward-compatible generic preview mutation guard."""
    await _require_preview_surface_enabled(session)
    await _require_preview_writes_enabled(session)
    _record_window_event(
        f"preview-agent:{agent.id}",
        limit=settings.PREVIEW_AGENT_MUTATIONS_PER_WINDOW,
        window_seconds=settings.PREVIEW_MUTATION_WINDOW_SECONDS,
        detail="Preview mutation rate limit exceeded.",
        error_code="preview_mutation_rate_limited",
    )


async def require_warfare_preview_write(
    agent: Any = Depends(get_current_agent),
    session: AsyncSession = Depends(get_session),
) -> None:
    """Guard warfare preview mutations behind the extra warfare toggle."""
    await _require_preview_surface_enabled(session)
    await _require_preview_writes_enabled(session)
    await _require_warfare_mutations_enabled(session)
    await _require_family_degraded_policy(
        session,
        "warfare",
        allow_in_degraded_mode=False,
    )
    await _apply_agent_policy_gate(
        session,
        agent_id=agent.id,
        family="warfare",
        consume_budget=False,
    )
    _record_agent_mutation(agent.id, "warfare")
    await _apply_agent_policy_gate(
        session,
        agent_id=agent.id,
        family="warfare",
        consume_budget=True,
    )


async def require_control_plane_admin(
    admin_token: str | None = Security(admin_token_header),
) -> str:
    """Protect mutable control-plane actions behind a static admin token."""
    expected = settings.CONTROL_PLANE_ADMIN_TOKEN
    if not expected:
        raise _guard_exception(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Control-plane admin token is not configured.",
            error_code="control_plane_admin_unconfigured",
        )
    if admin_token != expected:
        raise _guard_exception(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid control-plane admin token.",
            error_code="control_plane_admin_invalid",
        )
    token_fingerprint = hashlib.sha256(admin_token.encode()).hexdigest()[:8]
    return f"control-plane-admin:{token_fingerprint}"


async def get_preview_guard_state(session: AsyncSession) -> dict[str, Any]:
    """Return the currently effective preview control-plane state."""
    effective = await _get_effective_global_policy(session)
    agent_policy_count = int(
        (
            await session.execute(
                select(func.count(PreviewAgentPolicy.agent_id))
            )
        ).scalar_one()
        or 0
    )
    audit_log_size = int(
        (
            await session.execute(
                select(func.count(ControlPlaneAuditLog.id))
            )
        ).scalar_one()
        or 0
    )
    return {
        **effective,
        "mutation_window_seconds": settings.PREVIEW_MUTATION_WINDOW_SECONDS,
        "agent_mutations_per_window": settings.PREVIEW_AGENT_MUTATIONS_PER_WINDOW,
        "registrations_per_window_per_host": settings.PREVIEW_REGISTRATIONS_PER_WINDOW_PER_HOST,
        "family_limits": {
            family: _family_limit(family)
            for family in sorted(_FAMILY_LIMIT_ATTRS)
        },
        "agent_policy_count": agent_policy_count,
        "audit_log_size": audit_log_size,
        "policy_features": {
            "authenticated_read_policy": "family_scoped",
            "authenticated_write_policy": "family_scoped_with_budget",
            "public_preview_read_policy": "surface_only",
            "admin_action_context": "structured_reason_note",
            "budget_refill_support": True,
            "audit_filter_support": True,
            "audit_request_id_filtering": True,
            "stable_error_codes": True,
            "persistent_policy_store": True,
        },
        "rate_limit_store": "process_local_best_effort",
        "persistent_policy_store": "database",
        "error_codes": dict(ERROR_CODE_CATALOG),
        "admin_api": {
            "path": "/meta/control-plane",
            "configured": bool(settings.CONTROL_PLANE_ADMIN_TOKEN),
            "token_header": "X-Control-Plane-Token",
            "request_id_header": REQUEST_ID_HEADER,
            "error_code_header": ERROR_CODE_HEADER,
        },
    }


async def get_control_plane_admin_snapshot(
    session: AsyncSession,
    *,
    audit_limit: int = 20,
) -> dict[str, Any]:
    """Return the admin-facing snapshot including actor policy and audit detail."""
    state = await get_preview_guard_state(session)
    policy_result = await session.execute(
        select(PreviewAgentPolicy).order_by(PreviewAgentPolicy.agent_id.asc())
    )
    audit_result = await session.execute(
        select(ControlPlaneAuditLog)
        .order_by(ControlPlaneAuditLog.id.desc())
        .limit(max(audit_limit, 0))
    )
    state["agent_policies"] = [
        _serialize_agent_policy(policy)
        for policy in policy_result.scalars().all()
    ]
    state["recent_audit_entries"] = [
        _serialize_audit_entry(entry)
        for entry in audit_result.scalars().all()
    ]
    return state


async def update_preview_guard_state(
    session: AsyncSession,
    *,
    surface_enabled: bool | None = None,
    writes_enabled: bool | None = None,
    warfare_mutations_enabled: bool | None = None,
    degraded_mode: bool | None = None,
    audit_actor: str | None = None,
    request_id: str | None = None,
    client_fingerprint: str | None = None,
    reason_code: str | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    """Apply durable runtime overrides to the preview policy."""
    state = await _get_or_create_control_plane_state(session)
    updates = {
        "surface_enabled_override": surface_enabled,
        "writes_enabled_override": writes_enabled,
        "warfare_mutations_enabled_override": warfare_mutations_enabled,
        "degraded_mode_override": degraded_mode,
    }
    for key, value in updates.items():
        if value is not None:
            setattr(state, key, value)
    await session.flush()

    if audit_actor and any(value is not None for value in updates.values()):
        await _record_admin_action(
            session,
            "update_preview_runtime_policy",
            actor=audit_actor,
            request_id=request_id,
            client_fingerprint=client_fingerprint,
            reason_code=reason_code,
            note=note,
            payload={key: value for key, value in updates.items() if value is not None},
        )
    return await get_preview_guard_state(session)


async def upsert_agent_preview_policy(
    session: AsyncSession,
    agent_id: int,
    *,
    allowed_families: list[str] | None = None,
    family_budgets: dict[str, int] | None = None,
    audit_actor: str | None = None,
    request_id: str | None = None,
    client_fingerprint: str | None = None,
    reason_code: str | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    """Upsert a durable per-agent preview policy."""
    normalized_families = _normalize_allowed_families(allowed_families)
    normalized_budgets = _normalize_family_budgets(family_budgets)
    policy = await _get_agent_policy(session, agent_id, for_update=True)
    if policy is None:
        policy = PreviewAgentPolicy(
            agent_id=agent_id,
            allowed_families=normalized_families,
            family_budgets=normalized_budgets,
        )
        session.add(policy)
    else:
        policy.allowed_families = normalized_families
        policy.family_budgets = normalized_budgets
    await session.flush()

    if audit_actor:
        await _record_admin_action(
            session,
            "upsert_agent_preview_policy",
            actor=audit_actor,
            target_agent_id=agent_id,
            request_id=request_id,
            client_fingerprint=client_fingerprint,
            reason_code=reason_code,
            note=note,
            payload={
                "allowed_families": normalized_families,
                "family_budgets": normalized_budgets,
            },
        )
    return _serialize_agent_policy(policy)


async def clear_agent_preview_policy(
    session: AsyncSession,
    agent_id: int,
    *,
    audit_actor: str | None = None,
    request_id: str | None = None,
    client_fingerprint: str | None = None,
    reason_code: str | None = None,
    note: str | None = None,
) -> bool:
    """Delete a durable per-agent preview policy."""
    policy = await _get_agent_policy(session, agent_id, for_update=True)
    if policy is None:
        return False
    await session.delete(policy)
    await session.flush()
    if audit_actor:
        await _record_admin_action(
            session,
            "clear_agent_preview_policy",
            actor=audit_actor,
            target_agent_id=agent_id,
            request_id=request_id,
            client_fingerprint=client_fingerprint,
            reason_code=reason_code,
            note=note,
        )
    return True


async def refill_agent_preview_budget(
    session: AsyncSession,
    agent_id: int,
    *,
    increments: dict[str, int],
    audit_actor: str | None = None,
    request_id: str | None = None,
    client_fingerprint: str | None = None,
    reason_code: str | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    """Increment durable per-agent family budgets."""
    normalized = _normalize_family_budgets(increments)
    if not normalized:
        raise ValueError("At least one preview family budget increment is required.")
    for family, amount in normalized.items():
        if amount <= 0:
            raise ValueError(f"Preview budget refill for {family} must be > 0")

    policy = await _get_agent_policy(session, agent_id, for_update=True)
    if policy is None:
        policy = PreviewAgentPolicy(
            agent_id=agent_id,
            allowed_families=None,
            family_budgets={},
        )
        session.add(policy)
        await session.flush()

    budgets = dict(policy.family_budgets or {})
    for family, amount in normalized.items():
        budgets[family] = int(budgets.get(family, 0)) + amount
    policy.family_budgets = budgets
    await session.flush()

    if audit_actor:
        await _record_admin_action(
            session,
            "refill_agent_preview_budget",
            actor=audit_actor,
            target_agent_id=agent_id,
            request_id=request_id,
            client_fingerprint=client_fingerprint,
            reason_code=reason_code,
            note=note,
            payload={"increments": normalized},
        )
    return _serialize_agent_policy(policy)


async def reset_preview_guard_runtime(
    session: AsyncSession,
    *,
    audit_actor: str | None = None,
    request_id: str | None = None,
    client_fingerprint: str | None = None,
    reason_code: str | None = None,
    note: str | None = None,
) -> None:
    """Clear process-local rate-limit windows while preserving durable policy."""
    with _mutation_lock:
        _mutation_windows.clear()
    if audit_actor:
        await _record_admin_action(
            session,
            "reset_preview_guard_runtime",
            actor=audit_actor,
            request_id=request_id,
            client_fingerprint=client_fingerprint,
            reason_code=reason_code,
            note=note,
            payload={"scope": "rate_limits_only"},
        )


async def list_control_plane_audit(
    session: AsyncSession,
    *,
    limit: int = 20,
    action: str | None = None,
    target_agent_id: int | None = None,
    reason_code: str | None = None,
    request_id: str | None = None,
) -> list[dict[str, Any]]:
    """Return recent admin actions for the durable preview policy."""
    stmt = select(ControlPlaneAuditLog)
    if action is not None:
        stmt = stmt.where(ControlPlaneAuditLog.action == action)
    if target_agent_id is not None:
        stmt = stmt.where(ControlPlaneAuditLog.target_agent_id == target_agent_id)
    if reason_code is not None:
        stmt = stmt.where(ControlPlaneAuditLog.reason_code == reason_code)
    if request_id is not None:
        stmt = stmt.where(ControlPlaneAuditLog.request_id == request_id)
    stmt = stmt.order_by(ControlPlaneAuditLog.id.desc()).limit(max(limit, 0))
    result = await session.execute(stmt)
    return [
        _serialize_audit_entry(entry)
        for entry in result.scalars().all()
    ]


def reset_preview_guard_state() -> None:
    """Clear process-local guard state for deterministic tests."""
    with _mutation_lock:
        _mutation_windows.clear()


async def hydrate_preview_guard_runtime(session: AsyncSession) -> dict[str, Any]:
    """Compatibility hook for startup/runtime metadata refresh."""
    return await get_preview_guard_state(session)
