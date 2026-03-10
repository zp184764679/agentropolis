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

    concurrency = observability["concurrency"]
    request_capacity = max(int(concurrency["request_slots"]["capacity"]), 1)
    request_in_use = int(concurrency["request_slots"]["in_use"])
    if request_in_use / request_capacity >= 0.8:
        alerts.append(
            _alert(
                "concurrency_request_slot_saturation",
                "warning",
                "Authenticated request slot usage is above 80% of configured capacity.",
                source="concurrency",
            )
        )
    if int(concurrency["recent_failures"]["slot_timeouts"]) > 0:
        alerts.append(
            _alert(
                "concurrency_slot_timeouts_present",
                "critical",
                "One or more authenticated requests timed out waiting for a concurrency slot.",
                source="concurrency",
            )
        )
    if int(concurrency["recent_failures"]["entity_lock_timeouts"]) > 0:
        alerts.append(
            _alert(
                "concurrency_entity_lock_timeouts_present",
                "warning",
                "One or more authenticated mutations timed out on entity lock acquisition.",
                source="concurrency",
            )
        )

    preview_policy = observability["preview_policy"]
    if int(preview_policy["exhausted_operation_budget_policies"]) > 0:
        alerts.append(
            _alert(
                "preview_operation_budgets_exhausted",
                "warning",
                "One or more preview policies have exhausted dangerous-operation budgets.",
                source="preview_policy",
            )
        )
    if int(preview_policy["critical_spend_budget_policies"]) > 0:
        alerts.append(
            _alert(
                "preview_spend_budget_critical",
                "critical",
                "One or more preview policies are at or below the critical remaining spend budget threshold.",
                source="preview_policy",
            )
        )
    elif int(preview_policy["low_spend_budget_policies"]) > 0:
        alerts.append(
            _alert(
                "preview_spend_budget_low",
                "warning",
                "One or more preview policies are approaching their remaining spend budget threshold.",
                source="preview_policy",
            )
        )

    severity_by_gate = {
        "control_contract": "critical",
        "authz": "critical",
        "concurrency_guard": "critical",
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
            "alerts_endpoint": "/meta/alerts",
            "observability_endpoint": "/meta/observability",
            "rollout_readiness_endpoint": "/meta/rollout-readiness",
        },
    }
