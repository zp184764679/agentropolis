"""Process-local authenticated concurrency and entity-lock helpers."""

from __future__ import annotations

import asyncio
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from dataclasses import dataclass
import hashlib
from threading import Lock
from time import monotonic
from typing import Any

from fastapi import HTTPException, status

from agentropolis.config import settings

ERROR_CODE_HEADER = "X-Agentropolis-Error-Code"
CONCURRENCY_ERROR_CODES = {
    "concurrency_rate_limited": "Authenticated request rate limit exceeded.",
    "concurrency_slot_timeout": "Authenticated request concurrency slots are exhausted.",
    "concurrency_entity_lock_timeout": "Entity lock acquisition timed out for this authenticated mutation.",
}

_WINDOW_LOCK = Lock()
_COUNTER_LOCK = Lock()
_RATE_LIMIT_WINDOWS: dict[str, deque[float]] = defaultdict(deque)
_COUNTERS = {
    "rate_limit_hits": 0,
    "slot_timeouts": 0,
    "entity_lock_timeouts": 0,
}
_RUNTIME_LOCK = Lock()
_RUNTIMES: dict[int, "_LoopConcurrencyRuntime"] = {}


@dataclass
class _LoopConcurrencyRuntime:
    request_slots: asyncio.Semaphore
    housekeeping_slots: asyncio.Semaphore
    striped_locks: list[asyncio.Lock]
    request_slots_in_use: int = 0
    housekeeping_slots_in_use: int = 0


def _raise_concurrency_error(
    *,
    status_code: int,
    detail: str,
    error_code: str,
    headers: dict[str, str] | None = None,
) -> None:
    merged = dict(headers or {})
    merged[ERROR_CODE_HEADER] = error_code
    raise HTTPException(
        status_code=status_code,
        detail=detail,
        headers=merged,
    )


def _increment_counter(name: str) -> None:
    with _COUNTER_LOCK:
        _COUNTERS[name] = int(_COUNTERS.get(name, 0)) + 1


def _current_runtime() -> _LoopConcurrencyRuntime:
    loop = asyncio.get_running_loop()
    key = id(loop)
    with _RUNTIME_LOCK:
        runtime = _RUNTIMES.get(key)
        if runtime is None:
            request_capacity = max(
                1,
                int(settings.CONCURRENCY_MAX_CONCURRENT)
                - int(settings.HOUSEKEEPING_RESERVED_SLOTS),
            )
            housekeeping_capacity = max(1, int(settings.HOUSEKEEPING_RESERVED_SLOTS))
            runtime = _LoopConcurrencyRuntime(
                request_slots=asyncio.Semaphore(request_capacity),
                housekeeping_slots=asyncio.Semaphore(housekeeping_capacity),
                striped_locks=[
                    asyncio.Lock()
                    for _ in range(max(1, int(settings.CONCURRENCY_STRIPE_COUNT)))
                ],
            )
            _RUNTIMES[key] = runtime
    return runtime


def _actor_limit(actor_kind: str) -> int:
    if actor_kind == "admin":
        return int(settings.RATE_LIMIT_ADMIN_REQUESTS_PER_WINDOW)
    if actor_kind == "company":
        return int(settings.RATE_LIMIT_COMPANY_REQUESTS_PER_WINDOW)
    return int(settings.RATE_LIMIT_AGENT_REQUESTS_PER_WINDOW)


def _stripe_index(lock_key: str) -> int:
    digest = hashlib.sha256(lock_key.encode("utf-8")).hexdigest()
    return int(digest, 16) % max(1, int(settings.CONCURRENCY_STRIPE_COUNT))


def classify_authenticated_actor(
    *,
    path: str,
    api_key: str | None,
    admin_token: str | None,
) -> tuple[str, str] | None:
    if admin_token:
        return "admin", f"admin:{hashlib.sha256(admin_token.encode()).hexdigest()}"
    if not api_key:
        return None
    company_paths = {
        "/api/company/status",
        "/api/company/workers",
    }
    company_prefixes = (
        "/api/market",
        "/api/production",
        "/api/inventory",
    )
    actor_kind = "company" if path in company_paths or path.startswith(company_prefixes) else "agent"
    return actor_kind, f"{actor_kind}:{hashlib.sha256(api_key.encode()).hexdigest()}"


def enforce_authenticated_request_rate_limit(actor_kind: str, actor_key: str) -> None:
    limit = _actor_limit(actor_kind)
    if limit <= 0:
        return

    window_seconds = int(settings.RATE_LIMIT_WINDOW_SECONDS)
    now = monotonic()
    cutoff = now - window_seconds
    with _WINDOW_LOCK:
        bucket = _RATE_LIMIT_WINDOWS[actor_key]
        while bucket and bucket[0] <= cutoff:
            bucket.popleft()
        if len(bucket) >= limit:
            _increment_counter("rate_limit_hits")
            _raise_concurrency_error(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Authenticated request rate limit exceeded.",
                error_code="concurrency_rate_limited",
                headers={"Retry-After": str(window_seconds)},
            )
        bucket.append(now)


@asynccontextmanager
async def acquire_request_slot() -> Any:
    runtime = _current_runtime()
    try:
        await asyncio.wait_for(
            runtime.request_slots.acquire(),
            timeout=float(settings.CONCURRENCY_SLOT_TIMEOUT),
        )
    except TimeoutError:
        _increment_counter("slot_timeouts")
        _raise_concurrency_error(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authenticated request concurrency slots are exhausted.",
            error_code="concurrency_slot_timeout",
        )

    runtime.request_slots_in_use += 1
    try:
        yield
    finally:
        runtime.request_slots_in_use = max(0, runtime.request_slots_in_use - 1)
        runtime.request_slots.release()


@asynccontextmanager
async def acquire_housekeeping_slot() -> Any:
    runtime = _current_runtime()
    try:
        await asyncio.wait_for(
            runtime.housekeeping_slots.acquire(),
            timeout=float(settings.CONCURRENCY_SLOT_TIMEOUT),
        )
    except TimeoutError:
        _increment_counter("slot_timeouts")
        raise RuntimeError("Housekeeping concurrency slots are exhausted.") from None

    runtime.housekeeping_slots_in_use += 1
    try:
        yield
    finally:
        runtime.housekeeping_slots_in_use = max(0, runtime.housekeeping_slots_in_use - 1)
        runtime.housekeeping_slots.release()


@asynccontextmanager
async def acquire_entity_locks(lock_keys: list[str] | tuple[str, ...]) -> Any:
    normalized = sorted({key for key in lock_keys if key})
    if not normalized:
        yield {"lock_keys": [], "stripe_indices": []}
        return

    runtime = _current_runtime()
    stripe_indices = sorted({_stripe_index(key) for key in normalized})
    acquired: list[asyncio.Lock] = []

    try:
        for stripe_index in stripe_indices:
            lock = runtime.striped_locks[stripe_index]
            try:
                await asyncio.wait_for(
                    lock.acquire(),
                    timeout=float(settings.CONCURRENCY_LOCK_TIMEOUT),
                )
            except TimeoutError:
                _increment_counter("entity_lock_timeouts")
                _raise_concurrency_error(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Entity lock acquisition timed out for this authenticated mutation.",
                    error_code="concurrency_entity_lock_timeout",
                    headers={"Retry-After": str(int(settings.CONCURRENCY_LOCK_TIMEOUT))},
                )
            acquired.append(lock)
        yield {
            "lock_keys": normalized,
            "stripe_indices": stripe_indices,
        }
    finally:
        for lock in reversed(acquired):
            lock.release()


def get_concurrency_snapshot() -> dict[str, Any]:
    with _COUNTER_LOCK:
        counters = dict(_COUNTERS)
    with _RUNTIME_LOCK:
        runtimes = list(_RUNTIMES.values())
    return {
        "process_local": True,
        "authenticated_request_scope": "all",
        "entity_lock_scope": "writes_only",
        "request_slots": {
            "capacity": max(
                1,
                int(settings.CONCURRENCY_MAX_CONCURRENT)
                - int(settings.HOUSEKEEPING_RESERVED_SLOTS),
            ),
            "in_use": sum(runtime.request_slots_in_use for runtime in runtimes),
            "timeout_seconds": float(settings.CONCURRENCY_SLOT_TIMEOUT),
        },
        "housekeeping_slots": {
            "capacity": max(1, int(settings.HOUSEKEEPING_RESERVED_SLOTS)),
            "in_use": sum(runtime.housekeeping_slots_in_use for runtime in runtimes),
        },
        "entity_locks": {
            "stripe_count": int(settings.CONCURRENCY_STRIPE_COUNT),
            "timeout_seconds": float(settings.CONCURRENCY_LOCK_TIMEOUT),
        },
        "rate_limits": {
            "window_seconds": int(settings.RATE_LIMIT_WINDOW_SECONDS),
            "agent": int(settings.RATE_LIMIT_AGENT_REQUESTS_PER_WINDOW),
            "company": int(settings.RATE_LIMIT_COMPANY_REQUESTS_PER_WINDOW),
            "admin": int(settings.RATE_LIMIT_ADMIN_REQUESTS_PER_WINDOW),
            "hits": counters["rate_limit_hits"],
        },
        "recent_failures": {
            "slot_timeouts": counters["slot_timeouts"],
            "entity_lock_timeouts": counters["entity_lock_timeouts"],
        },
        "error_codes": dict(CONCURRENCY_ERROR_CODES),
    }


def reset_concurrency_state() -> None:
    with _WINDOW_LOCK:
        _RATE_LIMIT_WINDOWS.clear()
    with _COUNTER_LOCK:
        for key in _COUNTERS:
            _COUNTERS[key] = 0
    with _RUNTIME_LOCK:
        _RUNTIMES.clear()


def agent_lock_key(agent_id: int) -> str:
    return f"agent:{agent_id}"


def company_lock_key(company_id: int) -> str:
    return f"company:{company_id}"


def guild_lock_key(guild_id: int) -> str:
    return f"guild:{guild_id}"


def treaty_lock_key(treaty_id: int) -> str:
    return f"treaty:{treaty_id}"


def contract_lock_key(contract_id: int) -> str:
    return f"contract:{contract_id}"


def building_lock_key(building_id: int) -> str:
    return f"building:{building_id}"


def preview_policy_lock_key(agent_id: int) -> str:
    return f"preview-policy:{agent_id}"


def control_plane_global_lock_key() -> str:
    return "control-plane:global"


def execution_job_lock_key(job_id: int) -> str:
    return f"execution-job:{job_id}"
