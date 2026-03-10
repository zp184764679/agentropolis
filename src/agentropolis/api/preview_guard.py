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
from threading import Lock
from time import monotonic
from typing import Any

from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import APIKeyHeader

from agentropolis.api.auth import get_current_agent
from agentropolis.config import settings

_mutation_windows: dict[str, deque[float]] = defaultdict(deque)
_mutation_lock = Lock()
_policy_lock = Lock()
_policy_overrides: dict[str, bool | None] = {
    "surface_enabled": None,
    "writes_enabled": None,
    "warfare_mutations_enabled": None,
    "degraded_mode": None,
}

admin_token_header = APIKeyHeader(name="X-Control-Plane-Token", auto_error=False)
_FAMILY_LIMIT_ATTRS = {
    "agent_self": "PREVIEW_AGENT_SELF_MUTATIONS_PER_WINDOW",
    "world": "PREVIEW_WORLD_MUTATIONS_PER_WINDOW",
    "transport": "PREVIEW_TRANSPORT_MUTATIONS_PER_WINDOW",
    "social": "PREVIEW_SOCIAL_MUTATIONS_PER_WINDOW",
    "strategy": "PREVIEW_STRATEGY_MUTATIONS_PER_WINDOW",
    "warfare": "PREVIEW_WARFARE_MUTATIONS_PER_WINDOW",
}


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
        _record_agent_mutation(agent.id, family)

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
    _record_agent_mutation(agent.id, "warfare")


async def require_control_plane_admin(
    admin_token: str | None = Security(admin_token_header),
) -> None:
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


def get_preview_guard_state() -> dict[str, Any]:
    """Return the currently effective preview control-plane state."""
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
        "rate_limit_store": "process_local_best_effort",
        "admin_api": {
            "path": "/meta/control-plane",
            "configured": bool(settings.CONTROL_PLANE_ADMIN_TOKEN),
            "token_header": "X-Control-Plane-Token",
        },
    }


def update_preview_guard_state(
    *,
    surface_enabled: bool | None = None,
    writes_enabled: bool | None = None,
    warfare_mutations_enabled: bool | None = None,
    degraded_mode: bool | None = None,
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
    return get_preview_guard_state()


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
