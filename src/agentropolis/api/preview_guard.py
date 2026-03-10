"""Best-effort control-plane guardrails for mounted preview routes.

This module is intentionally process-local and lightweight. It provides:
- a global preview-surface kill switch
- a preview write gate
- a warfare-specific write gate
- simple in-memory mutation throttling for preview actors

It is not a replacement for the planned distributed authz/quota/budget system.
"""

from __future__ import annotations

from collections import defaultdict, deque
from threading import Lock
from time import monotonic
from typing import Any

from fastapi import Depends, HTTPException, Request, status

from agentropolis.api.auth import get_current_agent
from agentropolis.config import settings

_mutation_windows: dict[str, deque[float]] = defaultdict(deque)
_mutation_lock = Lock()


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


def _require_preview_surface_enabled() -> None:
    if not settings.PREVIEW_SURFACE_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Preview surface is disabled by runtime policy.",
        )


def _require_preview_writes_enabled() -> None:
    if not settings.PREVIEW_WRITES_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Preview write operations are disabled by runtime policy.",
        )


def _require_warfare_mutations_enabled() -> None:
    if not settings.WARFARE_MUTATIONS_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Warfare preview mutations are disabled by runtime policy.",
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


async def require_agent_preview_write(agent: Any = Depends(get_current_agent)) -> None:
    """Guard generic preview mutations for an authenticated agent."""
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
    _record_window_event(
        f"preview-agent:{agent.id}",
        limit=settings.PREVIEW_AGENT_MUTATIONS_PER_WINDOW,
        window_seconds=settings.PREVIEW_MUTATION_WINDOW_SECONDS,
        detail="Preview mutation rate limit exceeded.",
    )


def build_preview_guard_metadata() -> dict[str, Any]:
    """Expose the current preview guard posture for `/meta/runtime`."""
    return {
        "surface_enabled": settings.PREVIEW_SURFACE_ENABLED,
        "writes_enabled": settings.PREVIEW_WRITES_ENABLED,
        "warfare_mutations_enabled": settings.WARFARE_MUTATIONS_ENABLED,
        "mutation_window_seconds": settings.PREVIEW_MUTATION_WINDOW_SECONDS,
        "agent_mutations_per_window": settings.PREVIEW_AGENT_MUTATIONS_PER_WINDOW,
        "registrations_per_window_per_host": settings.PREVIEW_REGISTRATIONS_PER_WINDOW_PER_HOST,
        "rate_limit_store": "process_local_best_effort",
    }


def reset_preview_guard_state() -> None:
    """Clear in-memory guard state for deterministic tests."""
    with _mutation_lock:
        _mutation_windows.clear()
