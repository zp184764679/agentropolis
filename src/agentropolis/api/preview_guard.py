"""Best-effort control-plane guardrails for mounted preview routes.

This module is intentionally process-local and lightweight. It provides:
- a global preview-surface kill switch
- a preview write gate
- a warfare-specific write gate
- a degraded-mode policy toggle
- simple in-memory mutation throttling for preview actors by route family

It is not a replacement for the planned distributed authz/quota/budget system.
"""

from __future__ import annotations

from collections import defaultdict, deque
from datetime import UTC, datetime
import hashlib
from itertools import count
from threading import Lock
from time import monotonic
from typing import Any

from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import APIKeyHeader

from agentropolis.api.auth import get_current_agent
from agentropolis.config import settings
from agentropolis.middleware import REQUEST_ID_HEADER

_mutation_windows: dict[str, deque[float]] = defaultdict(deque)
_mutation_lock = Lock()
_policy_lock = Lock()
_policy_overrides: dict[str, bool | None] = {
    "surface_enabled": None,
    "writes_enabled": None,
    "warfare_mutations_enabled": None,
    "degraded_mode": None,
}
_agent_policy_overrides: dict[int, dict[str, Any]] = {}
_audit_log: deque[dict[str, Any]] = deque(maxlen=200)
_audit_counter = count(1)

admin_token_header = APIKeyHeader(name="X-Control-Plane-Token", auto_error=False)
_FAMILY_LIMIT_ATTRS = {
    "agent_self": "PREVIEW_AGENT_SELF_MUTATIONS_PER_WINDOW",
    "world": "PREVIEW_WORLD_MUTATIONS_PER_WINDOW",
    "transport": "PREVIEW_TRANSPORT_MUTATIONS_PER_WINDOW",
    "social": "PREVIEW_SOCIAL_MUTATIONS_PER_WINDOW",
    "strategy": "PREVIEW_STRATEGY_MUTATIONS_PER_WINDOW",
    "warfare": "PREVIEW_WARFARE_MUTATIONS_PER_WINDOW",
}


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _record_window_event(
    key: str,
    *,
    limit: int,
    window_seconds: int,
    detail: str,
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
                headers={"Retry-After": str(window_seconds)},
            )

        bucket.append(now)


def _client_fingerprint(request: Request) -> str:
    client = request.client
    if client is None:
        return "unknown"
    return f"{client.host}:{client.port}"


def _policy_value(name: str, default: bool) -> bool:
    with _policy_lock:
        override = _policy_overrides[name]
    return default if override is None else override


def _preview_surface_enabled() -> bool:
    return _policy_value("surface_enabled", settings.PREVIEW_SURFACE_ENABLED)


def _preview_writes_enabled() -> bool:
    return _policy_value("writes_enabled", settings.PREVIEW_WRITES_ENABLED)


def _warfare_mutations_enabled() -> bool:
    return _policy_value(
        "warfare_mutations_enabled",
        settings.WARFARE_MUTATIONS_ENABLED,
    )


def _preview_degraded_mode() -> bool:
    return _policy_value("degraded_mode", settings.PREVIEW_DEGRADED_MODE)


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
        if budget < 0:
            raise ValueError(f"Preview budget for {family} must be >= 0")
        normalized[family] = int(budget)
    return normalized


def _policy_entry(agent_id: int) -> dict[str, Any] | None:
    with _policy_lock:
        policy = _agent_policy_overrides.get(agent_id)
        if policy is None:
            return None
        return {
            "agent_id": policy["agent_id"],
            "allowed_families": list(policy["allowed_families"])
            if policy["allowed_families"] is not None
            else None,
            "family_budgets": dict(policy["family_budgets"]),
            "updated_at": policy["updated_at"],
        }


def _record_admin_action(
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
    entry = {
        "event_id": next(_audit_counter),
        "action": action,
        "actor": actor,
        "target_agent_id": target_agent_id,
        "request_id": request_id,
        "client_fingerprint": client_fingerprint,
        "reason_code": reason_code,
        "note": note,
        "payload": payload or {},
        "occurred_at": _utc_now(),
    }
    with _policy_lock:
        _audit_log.appendleft(entry)


def _require_agent_family_authorized(agent_id: int, family: str) -> None:
    policy = _policy_entry(agent_id)
    if policy is None or policy["allowed_families"] is None:
        return
    if family not in policy["allowed_families"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Preview {family} access is not allowed for agent {agent_id}.",
        )


def make_agent_preview_access_guard(family: str):
    """Build a dependency that guards authenticated preview reads for one route family."""

    async def dependency(agent: Any = Depends(get_current_agent)) -> None:
        _require_preview_surface_enabled()
        _require_agent_family_authorized(agent.id, family)

    return dependency


def _consume_agent_budget(agent_id: int, family: str) -> None:
    with _policy_lock:
        policy = _agent_policy_overrides.get(agent_id)
        if policy is None:
            return
        family_budgets = policy["family_budgets"]
        if family not in family_budgets:
            return
        remaining = family_budgets[family]
        if remaining <= 0:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Preview {family} budget exhausted for agent {agent_id}.",
            )
        family_budgets[family] = remaining - 1
        policy["updated_at"] = _utc_now()


def _require_agent_budget_available(agent_id: int, family: str) -> None:
    policy = _policy_entry(agent_id)
    if policy is None:
        return
    remaining = policy["family_budgets"].get(family)
    if remaining is None:
        return
    if remaining <= 0:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Preview {family} budget exhausted for agent {agent_id}.",
        )


def _require_preview_surface_enabled() -> None:
    if not _preview_surface_enabled():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Preview surface is disabled by runtime policy.",
        )


def _require_preview_writes_enabled() -> None:
    if not _preview_writes_enabled():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Preview write operations are disabled by runtime policy.",
        )


def _require_warfare_mutations_enabled() -> None:
    if not _warfare_mutations_enabled():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Warfare preview mutations are disabled by runtime policy.",
        )


def _require_family_degraded_policy(
    family: str,
    *,
    allow_in_degraded_mode: bool,
) -> None:
    if _preview_degraded_mode() and not allow_in_degraded_mode:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Preview {family} mutations are disabled in degraded mode.",
        )


def _record_agent_mutation(agent_id: Any, family: str) -> None:
    _record_window_event(
        f"preview-family:{family}:agent:{agent_id}",
        limit=_family_limit(family),
        window_seconds=settings.PREVIEW_MUTATION_WINDOW_SECONDS,
        detail=f"Preview {family} mutation rate limit exceeded.",
    )


async def require_preview_surface() -> None:
    """Block all mounted preview routes behind a global runtime switch."""
    _require_preview_surface_enabled()


async def require_preview_registration_write(request: Request) -> None:
    """Guard unauthenticated agent registration on the preview surface."""
    _require_preview_surface_enabled()
    _require_preview_writes_enabled()
    _record_window_event(
        f"preview-registration:{_client_fingerprint(request)}",
        limit=settings.PREVIEW_REGISTRATIONS_PER_WINDOW_PER_HOST,
        window_seconds=settings.PREVIEW_MUTATION_WINDOW_SECONDS,
        detail="Preview registration rate limit exceeded.",
    )


def make_agent_preview_write_guard(
    family: str,
    *,
    allow_in_degraded_mode: bool = False,
):
    """Build a dependency that guards preview mutations for one route family."""

    async def dependency(agent: Any = Depends(get_current_agent)) -> None:
        _require_preview_surface_enabled()
        _require_preview_writes_enabled()
        _require_family_degraded_policy(
            family,
            allow_in_degraded_mode=allow_in_degraded_mode,
        )
        _require_agent_family_authorized(agent.id, family)
        _require_agent_budget_available(agent.id, family)
        _record_agent_mutation(agent.id, family)
        _consume_agent_budget(agent.id, family)

    return dependency


async def require_agent_preview_write(agent: Any = Depends(get_current_agent)) -> None:
    """Backward-compatible generic preview mutation guard."""
    _require_preview_surface_enabled()
    _require_preview_writes_enabled()
    _record_window_event(
        f"preview-agent:{agent.id}",
        limit=settings.PREVIEW_AGENT_MUTATIONS_PER_WINDOW,
        window_seconds=settings.PREVIEW_MUTATION_WINDOW_SECONDS,
        detail="Preview mutation rate limit exceeded.",
    )


async def require_warfare_preview_write(agent: Any = Depends(get_current_agent)) -> None:
    """Guard warfare preview mutations behind an extra kill switch."""
    _require_preview_surface_enabled()
    _require_preview_writes_enabled()
    _require_warfare_mutations_enabled()
    _require_family_degraded_policy("warfare", allow_in_degraded_mode=False)
    _require_agent_family_authorized(agent.id, "warfare")
    _require_agent_budget_available(agent.id, "warfare")
    _record_agent_mutation(agent.id, "warfare")
    _consume_agent_budget(agent.id, "warfare")


async def require_control_plane_admin(
    admin_token: str | None = Security(admin_token_header),
) -> str:
    """Protect mutable control-plane actions behind a static admin token."""
    expected = settings.CONTROL_PLANE_ADMIN_TOKEN
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Control-plane admin token is not configured.",
        )
    if admin_token != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid control-plane admin token.",
        )
    token_fingerprint = hashlib.sha256(admin_token.encode()).hexdigest()[:8]
    return f"control-plane-admin:{token_fingerprint}"


def get_preview_guard_state() -> dict[str, Any]:
    """Return the currently effective preview control-plane state."""
    with _policy_lock:
        agent_policy_count = len(_agent_policy_overrides)
        audit_log_size = len(_audit_log)
    return {
        "surface_enabled": _preview_surface_enabled(),
        "writes_enabled": _preview_writes_enabled(),
        "warfare_mutations_enabled": _warfare_mutations_enabled(),
        "degraded_mode": _preview_degraded_mode(),
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
        },
        "rate_limit_store": "process_local_best_effort",
        "admin_api": {
            "path": "/meta/control-plane",
            "configured": bool(settings.CONTROL_PLANE_ADMIN_TOKEN),
            "token_header": "X-Control-Plane-Token",
            "request_id_header": REQUEST_ID_HEADER,
        },
    }


def get_control_plane_admin_snapshot(*, audit_limit: int = 20) -> dict[str, Any]:
    """Return the admin-facing snapshot including actor policy and audit detail."""
    state = get_preview_guard_state()
    with _policy_lock:
        policies = [
            {
                "agent_id": policy["agent_id"],
                "allowed_families": list(policy["allowed_families"])
                if policy["allowed_families"] is not None
                else None,
                "family_budgets": dict(policy["family_budgets"]),
                "updated_at": policy["updated_at"],
            }
            for policy in sorted(
                _agent_policy_overrides.values(),
                key=lambda item: item["agent_id"],
            )
        ]
        recent_audit_entries = list(_audit_log)[: max(audit_limit, 0)]
    state["agent_policies"] = policies
    state["recent_audit_entries"] = recent_audit_entries
    return state


def update_preview_guard_state(
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
    """Apply runtime overrides to the process-local preview policy."""
    updates = {
        "surface_enabled": surface_enabled,
        "writes_enabled": writes_enabled,
        "warfare_mutations_enabled": warfare_mutations_enabled,
        "degraded_mode": degraded_mode,
    }
    with _policy_lock:
        for key, value in updates.items():
            if value is not None:
                _policy_overrides[key] = value
    if audit_actor and any(value is not None for value in updates.values()):
        _record_admin_action(
            "update_preview_runtime_policy",
            actor=audit_actor,
            request_id=request_id,
            client_fingerprint=client_fingerprint,
            reason_code=reason_code,
            note=note,
            payload={key: value for key, value in updates.items() if value is not None},
        )
    return get_preview_guard_state()


def upsert_agent_preview_policy(
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
    """Upsert a process-local per-agent preview policy."""
    normalized_families = _normalize_allowed_families(allowed_families)
    normalized_budgets = _normalize_family_budgets(family_budgets)
    policy = {
        "agent_id": agent_id,
        "allowed_families": normalized_families,
        "family_budgets": normalized_budgets,
        "updated_at": _utc_now(),
    }
    with _policy_lock:
        _agent_policy_overrides[agent_id] = policy
    if audit_actor:
        _record_admin_action(
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
    return _policy_entry(agent_id) or policy


def clear_agent_preview_policy(
    agent_id: int,
    *,
    audit_actor: str | None = None,
    request_id: str | None = None,
    client_fingerprint: str | None = None,
    reason_code: str | None = None,
    note: str | None = None,
) -> bool:
    """Delete a process-local per-agent preview policy."""
    with _policy_lock:
        existed = _agent_policy_overrides.pop(agent_id, None) is not None
    if existed and audit_actor:
        _record_admin_action(
            "clear_agent_preview_policy",
            actor=audit_actor,
            target_agent_id=agent_id,
            request_id=request_id,
            client_fingerprint=client_fingerprint,
            reason_code=reason_code,
            note=note,
        )
    return existed


def refill_agent_preview_budget(
    agent_id: int,
    *,
    increments: dict[str, int],
    audit_actor: str | None = None,
    request_id: str | None = None,
    client_fingerprint: str | None = None,
    reason_code: str | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    """Increment process-local per-agent family budgets."""
    normalized = _normalize_family_budgets(increments)
    if not normalized:
        raise ValueError("At least one preview family budget increment is required.")
    for family, amount in normalized.items():
        if amount <= 0:
            raise ValueError(f"Preview budget refill for {family} must be > 0")

    with _policy_lock:
        policy = _agent_policy_overrides.get(agent_id)
        if policy is None:
            policy = {
                "agent_id": agent_id,
                "allowed_families": None,
                "family_budgets": {},
                "updated_at": _utc_now(),
            }
            _agent_policy_overrides[agent_id] = policy

        for family, amount in normalized.items():
            policy["family_budgets"][family] = policy["family_budgets"].get(family, 0) + amount
        policy["updated_at"] = _utc_now()

    if audit_actor:
        _record_admin_action(
            "refill_agent_preview_budget",
            actor=audit_actor,
            target_agent_id=agent_id,
            request_id=request_id,
            client_fingerprint=client_fingerprint,
            reason_code=reason_code,
            note=note,
            payload={"increments": normalized},
        )
    return _policy_entry(agent_id) or policy


def reset_preview_guard_runtime(
    *,
    audit_actor: str | None = None,
    request_id: str | None = None,
    client_fingerprint: str | None = None,
    reason_code: str | None = None,
    note: str | None = None,
) -> None:
    """Clear process-local runtime counters and overrides while preserving code defaults."""
    with _mutation_lock:
        _mutation_windows.clear()
    with _policy_lock:
        for key in _policy_overrides:
            _policy_overrides[key] = None
        _agent_policy_overrides.clear()
    if audit_actor:
        _record_admin_action(
            "reset_preview_guard_runtime",
            actor=audit_actor,
            request_id=request_id,
            client_fingerprint=client_fingerprint,
            reason_code=reason_code,
            note=note,
        )


def list_control_plane_audit(
    *,
    limit: int = 20,
    action: str | None = None,
    target_agent_id: int | None = None,
    reason_code: str | None = None,
) -> list[dict[str, Any]]:
    """Return recent admin actions for the process-local preview policy."""
    with _policy_lock:
        entries = list(_audit_log)

    if action is not None:
        entries = [entry for entry in entries if entry["action"] == action]
    if target_agent_id is not None:
        entries = [entry for entry in entries if entry["target_agent_id"] == target_agent_id]
    if reason_code is not None:
        entries = [entry for entry in entries if entry["reason_code"] == reason_code]
    return entries[: max(limit, 0)]


def build_preview_guard_metadata() -> dict[str, Any]:
    """Expose the current preview guard posture for `/meta/runtime`."""
    return get_preview_guard_state()


def reset_preview_guard_state() -> None:
    """Clear in-memory guard state for deterministic tests."""
    with _mutation_lock:
        _mutation_windows.clear()
    with _policy_lock:
        for key in _policy_overrides:
            _policy_overrides[key] = None
        _agent_policy_overrides.clear()
        _audit_log.clear()
