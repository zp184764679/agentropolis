"""Process-local request metrics for migration-phase observability."""

from __future__ import annotations

from collections import defaultdict, deque
import logging
from threading import Lock
from time import monotonic

from agentropolis.config import settings
from agentropolis.services.structured_logging import emit_structured_log
from starlette.middleware.base import BaseHTTPMiddleware

_LOCK = Lock()
_RECENT_LIMIT = 20
logger = logging.getLogger(__name__)
_STATE = {
    "requests_total": 0,
    "failures_total": 0,
    "slow_requests_total": 0,
    "by_method": defaultdict(int),
    "by_status": defaultdict(int),
    "by_actor_kind": defaultdict(int),
    "by_path": {},
    "recent_requests": deque(maxlen=_RECENT_LIMIT),
}


def _path_bucket(path: str) -> str:
    if path.startswith("/api/agent/profile/"):
        return "/api/agent/profile/{agent_id}"
    if path.startswith("/api/warfare/contracts/"):
        return "/api/warfare/contracts/{id}"
    return path


def record_request(
    method: str,
    path: str,
    status_code: int,
    duration_ms: float,
    *,
    actor_kind: str,
    request_id: str | None = None,
    error_code: str | None = None,
) -> None:
    bucket = _path_bucket(path)
    threshold = float(settings.OBSERVABILITY_SLOW_REQUEST_MS)
    with _LOCK:
        _STATE["requests_total"] += 1
        _STATE["by_actor_kind"][actor_kind] += 1
        _STATE["by_method"][method] += 1
        _STATE["by_status"][str(status_code)] += 1
        if status_code >= 400:
            _STATE["failures_total"] += 1
        if duration_ms >= threshold:
            _STATE["slow_requests_total"] += 1

        path_state = _STATE["by_path"].setdefault(
            bucket,
            {
                "count": 0,
                "error_count": 0,
                "slow_count": 0,
                "last_status": None,
                "avg_duration_ms": 0.0,
                "max_duration_ms": 0.0,
                "last_request_id": None,
                "last_actor_kind": None,
                "last_error_code": None,
            },
        )
        path_state["count"] += 1
        if status_code >= 400:
            path_state["error_count"] += 1
        if duration_ms >= threshold:
            path_state["slow_count"] += 1
        count = path_state["count"]
        path_state["avg_duration_ms"] = round(
            ((path_state["avg_duration_ms"] * (count - 1)) + duration_ms) / count,
            3,
        )
        path_state["max_duration_ms"] = round(max(path_state["max_duration_ms"], duration_ms), 3)
        path_state["last_status"] = status_code
        path_state["last_request_id"] = request_id
        path_state["last_actor_kind"] = actor_kind
        path_state["last_error_code"] = error_code

        _STATE["recent_requests"].append(
            {
                "method": method,
                "path": bucket,
                "actor_kind": actor_kind,
                "status_code": status_code,
                "duration_ms": round(duration_ms, 3),
                "request_id": request_id,
                "error_code": error_code,
            }
        )


def get_request_metrics_snapshot() -> dict:
    with _LOCK:
        requests_total = int(_STATE["requests_total"])
        failures_total = int(_STATE["failures_total"])
        return {
            "process_local": True,
            "requests_total": requests_total,
            "failures_total": failures_total,
            "error_rate": round(failures_total / requests_total, 4) if requests_total else 0.0,
            "slow_requests_total": int(_STATE["slow_requests_total"]),
            "slow_threshold_ms": float(settings.OBSERVABILITY_SLOW_REQUEST_MS),
            "by_method": dict(_STATE["by_method"]),
            "by_status": dict(_STATE["by_status"]),
            "by_actor_kind": dict(_STATE["by_actor_kind"]),
            "by_path": {
                path: dict(stats)
                for path, stats in _STATE["by_path"].items()
            },
            "recent_requests": list(_STATE["recent_requests"]),
        }


def reset_request_metrics_state() -> None:
    with _LOCK:
        _STATE["requests_total"] = 0
        _STATE["failures_total"] = 0
        _STATE["slow_requests_total"] = 0
        _STATE["by_method"].clear()
        _STATE["by_status"].clear()
        _STATE["by_actor_kind"].clear()
        _STATE["by_path"].clear()
        _STATE["recent_requests"].clear()


class RequestMetricsMiddleware(BaseHTTPMiddleware):
    """Record best-effort per-request metrics for the local preview runtime."""

    async def dispatch(self, request, call_next):
        started = monotonic()
        actor_kind = getattr(request.state, "authenticated_actor_kind", "public") or "public"
        request_id = getattr(request.state, "request_id", None)
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = (monotonic() - started) * 1000
            record_request(
                request.method,
                request.url.path,
                500,
                duration_ms,
                actor_kind=actor_kind,
                request_id=request_id,
                error_code=None,
            )
            emit_structured_log(
                logger,
                "request_complete",
                method=request.method,
                path=_path_bucket(request.url.path),
                status_code=500,
                duration_ms=round(duration_ms, 3),
                actor_kind=actor_kind,
                request_id=request_id,
                error_code=None,
                slow=duration_ms >= float(settings.OBSERVABILITY_SLOW_REQUEST_MS),
                unhandled_exception=True,
            )
            raise

        duration_ms = (monotonic() - started) * 1000
        error_code = response.headers.get("X-Agentropolis-Error-Code")
        record_request(
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
            actor_kind=actor_kind,
            request_id=request_id,
            error_code=error_code,
        )
        emit_structured_log(
            logger,
            "request_complete",
            method=request.method,
            path=_path_bucket(request.url.path),
            status_code=response.status_code,
            duration_ms=round(duration_ms, 3),
            actor_kind=actor_kind,
            request_id=request_id,
            error_code=error_code,
            slow=duration_ms >= float(settings.OBSERVABILITY_SLOW_REQUEST_MS),
        )
        return response
