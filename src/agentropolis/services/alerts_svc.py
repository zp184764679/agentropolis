"""Derived alert snapshot helpers for local-preview operations."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from agentropolis.services.observability_svc import build_observability_snapshot
from agentropolis.services.rollout_readiness_svc import build_rollout_readiness_snapshot


def _alert(code: str, severity: str, detail: str, *, source: str) -> dict:
    return {
        "code": code,
        "severity": severity,
        "detail": detail,
        "source": source,
    }


async def build_alert_snapshot(session: AsyncSession, runtime_meta: dict) -> dict:
    observability = await build_observability_snapshot(session)
    readiness = await build_rollout_readiness_snapshot(session, runtime_meta)

    alerts: list[dict] = []
    latest_housekeeping = observability["housekeeping"]["latest_sweep"]
    if latest_housekeeping is None:
        alerts.append(
            _alert(
                "housekeeping_missing",
                "warning",
                "No housekeeping sweep has been recorded in this runtime yet.",
                source="housekeeping",
            )
        )
    elif latest_housekeeping["error_count"] > 0:
        alerts.append(
            _alert(
                "housekeeping_errors_present",
                "critical",
                "The latest housekeeping sweep recorded one or more errors.",
                source="housekeeping",
            )
        )

    health_flags = observability["economy"]["health_flags"]
    if health_flags["inflation_critical"]:
        alerts.append(
            _alert(
                "inflation_critical",
                "critical",
                "Inflation index crossed the configured critical threshold.",
                source="economy",
            )
        )
    elif health_flags["inflation_warning"]:
        alerts.append(
            _alert(
                "inflation_warning",
                "warning",
                "Inflation index crossed the configured warning threshold.",
                source="economy",
            )
        )

    severity_by_gate = {
        "control_contract": "critical",
        "authz": "critical",
        "abuse_budget_guard": "critical",
        "observability": "warning",
        "recovery": "critical",
        "contract_parity": "warning",
        "admin_token_configured": "warning",
        "mcp_surface_enabled": "warning",
        "housekeeping_active": "warning",
    }
    for gate_name in readiness["blocking_failures"]:
        detail = readiness["gates"][gate_name]["detail"]
        alerts.append(
            _alert(
                f"rollout_gate_blocked:{gate_name}",
                severity_by_gate.get(gate_name, "warning"),
                detail,
                source="rollout_readiness",
            )
        )

    severity_counts = {
        "critical": sum(1 for alert in alerts if alert["severity"] == "critical"),
        "warning": sum(1 for alert in alerts if alert["severity"] == "warning"),
        "info": sum(1 for alert in alerts if alert["severity"] == "info"),
    }

    return {
        "alerts": alerts,
        "summary": {
            "critical": severity_counts["critical"],
            "warning": severity_counts["warning"],
            "info": severity_counts["info"],
            "has_blocking_failures": bool(readiness["blocking_failures"]),
        },
        "sources": {
            "observability_endpoint": "/meta/observability",
            "rollout_readiness_endpoint": "/meta/rollout-readiness",
        },
    }
