"""Process-local MCP tool metrics for local-preview observability."""

from __future__ import annotations

from collections import defaultdict, deque
from threading import Lock

from agentropolis.config import settings

_LOCK = Lock()
_RECENT_LIMIT = 20
_STATE = {
    "calls_total": 0,
    "failures_total": 0,
    "slow_calls_total": 0,
    "by_actor_kind": defaultdict(int),
    "by_tool": {},
    "recent_calls": deque(maxlen=_RECENT_LIMIT),
}


def record_mcp_call(
    *,
    tool_name: str,
    actor_kind: str,
    ok: bool,
    duration_ms: float,
    status_code: int | None = None,
    error_code: str | None = None,
) -> None:
    threshold = float(settings.OBSERVABILITY_SLOW_MCP_MS)
    with _LOCK:
        _STATE["calls_total"] += 1
        _STATE["by_actor_kind"][actor_kind] += 1
        if not ok:
            _STATE["failures_total"] += 1
        if duration_ms >= threshold:
            _STATE["slow_calls_total"] += 1

        tool_state = _STATE["by_tool"].setdefault(
            tool_name,
            {
                "count": 0,
                "failures": 0,
                "slow_count": 0,
                "avg_duration_ms": 0.0,
                "max_duration_ms": 0.0,
                "last_status": None,
                "last_error_code": None,
            },
        )
        tool_state["count"] += 1
        count = tool_state["count"]
        tool_state["avg_duration_ms"] = round(
            ((tool_state["avg_duration_ms"] * (count - 1)) + duration_ms) / count,
            3,
        )
        tool_state["max_duration_ms"] = round(max(tool_state["max_duration_ms"], duration_ms), 3)
        if not ok:
            tool_state["failures"] += 1
        if duration_ms >= threshold:
            tool_state["slow_count"] += 1
        tool_state["last_status"] = status_code
        tool_state["last_error_code"] = error_code

        _STATE["recent_calls"].append(
            {
                "tool_name": tool_name,
                "actor_kind": actor_kind,
                "ok": ok,
                "status_code": status_code,
                "duration_ms": round(duration_ms, 3),
                "error_code": error_code,
            }
        )


def get_mcp_metrics_snapshot() -> dict:
    with _LOCK:
        calls_total = int(_STATE["calls_total"])
        failures_total = int(_STATE["failures_total"])
        return {
            "process_local": True,
            "calls_total": calls_total,
            "failures_total": failures_total,
            "failure_rate": round(failures_total / calls_total, 4) if calls_total else 0.0,
            "slow_calls_total": int(_STATE["slow_calls_total"]),
            "slow_threshold_ms": float(settings.OBSERVABILITY_SLOW_MCP_MS),
            "by_actor_kind": dict(_STATE["by_actor_kind"]),
            "by_tool": {
                name: dict(stats)
                for name, stats in _STATE["by_tool"].items()
            },
            "recent_calls": list(_STATE["recent_calls"]),
        }


def reset_mcp_metrics_state() -> None:
    with _LOCK:
        _STATE["calls_total"] = 0
        _STATE["failures_total"] = 0
        _STATE["slow_calls_total"] = 0
        _STATE["by_actor_kind"].clear()
        _STATE["by_tool"].clear()
        _STATE["recent_calls"].clear()
