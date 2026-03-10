"""Process-local request metrics for migration-phase observability."""

from __future__ import annotations

from collections import defaultdict, deque
from threading import Lock
from time import monotonic

from starlette.middleware.base import BaseHTTPMiddleware

_LOCK = Lock()
_RECENT_LIMIT = 20
_STATE = {
    "requests_total": 0,
    "by_method": defaultdict(int),
    "by_status": defaultdict(int),
    "by_path": {},
    "recent_requests": deque(maxlen=_RECENT_LIMIT),
}


def _path_bucket(path: str) -> str:
    if path.startswith("/api/agent/profile/"):
        return "/api/agent/profile/{agent_id}"
    if path.startswith("/api/warfare/contracts/"):
        return "/api/warfare/contracts/{id}"
    return path


def record_request(method: str, path: str, status_code: int, duration_ms: float) -> None:
    bucket = _path_bucket(path)
    with _LOCK:
        _STATE["requests_total"] += 1
        _STATE["by_method"][method] += 1
        _STATE["by_status"][str(status_code)] += 1

        path_state = _STATE["by_path"].setdefault(
            bucket,
            {
                "count": 0,
                "last_status": None,
                "avg_duration_ms": 0.0,
                "max_duration_ms": 0.0,
            },
        )
        path_state["count"] += 1
        count = path_state["count"]
        path_state["avg_duration_ms"] = round(
            ((path_state["avg_duration_ms"] * (count - 1)) + duration_ms) / count,
            3,
        )
        path_state["max_duration_ms"] = round(max(path_state["max_duration_ms"], duration_ms), 3)
        path_state["last_status"] = status_code

        _STATE["recent_requests"].append(
            {
                "method": method,
                "path": bucket,
                "status_code": status_code,
                "duration_ms": round(duration_ms, 3),
            }
        )


def get_request_metrics_snapshot() -> dict:
    with _LOCK:
        return {
            "process_local": True,
            "requests_total": _STATE["requests_total"],
            "by_method": dict(_STATE["by_method"]),
            "by_status": dict(_STATE["by_status"]),
            "by_path": {
                path: dict(stats)
                for path, stats in _STATE["by_path"].items()
            },
            "recent_requests": list(_STATE["recent_requests"]),
        }


class RequestMetricsMiddleware(BaseHTTPMiddleware):
    """Record best-effort per-request metrics for the local preview runtime."""

    async def dispatch(self, request, call_next):
        started = monotonic()
        response = await call_next(request)
        duration_ms = (monotonic() - started) * 1000
        record_request(request.method, request.url.path, response.status_code, duration_ms)
        return response
