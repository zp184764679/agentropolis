"""Rollout readiness snapshot for local-preview external access gates."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentropolis.config import settings
from agentropolis.models import HousekeepingLog
from agentropolis.services.observability_svc import build_observability_snapshot


def _gate(ready: bool, detail: str, *, blocker: bool = True) -> dict:
    return {
        "ready": ready,
        "detail": detail,
        "blocker": blocker,
    }


async def build_rollout_readiness_snapshot(session: AsyncSession, runtime_meta: dict) -> dict:
    observability = await build_observability_snapshot(session)
    latest_housekeeping = (
        await session.execute(
            select(HousekeepingLog).order_by(HousekeepingLog.sweep_count.desc()).limit(1)
        )
    ).scalar_one_or_none()

    gates = {
        "control_contract": _gate(
            runtime_meta["control_contract_surface"]["minimum_contract_frozen"]
            and runtime_meta["control_contract_surface"]["scope_catalog_available"]
            and runtime_meta["control_contract_surface"]["error_taxonomy_available"]
            and runtime_meta["mcp_surface"]["transport_frozen"]
            and runtime_meta["mcp_surface"]["transport"] == "streamable-http"
            and runtime_meta["rest_surface"]["error_code_header"] == "X-Agentropolis-Error-Code",
            "MCP transport, contract versioning, error taxonomy, and scope catalogs are exposed through the frozen local-preview contract surface.",
        ),
        "authz": _gate(
            runtime_meta["control_plane_surface"]["persistent"]
            and runtime_meta["preview_guard"]["policy_features"]["authenticated_read_policy"]
            == "family_scoped",
            "DB-backed preview policy covers authenticated reads and writes by family.",
        ),
        "concurrency_guard": _gate(
            runtime_meta["concurrency_surface"]["enabled"]
            and runtime_meta["concurrency_surface"]["authenticated_request_scope"] == "all"
            and runtime_meta["concurrency_surface"]["housekeeping_reserved_slots"] > 0,
            "Authenticated requests are gated by process-local rate limits and global slots, with reserved housekeeping capacity.",
        ),
        "abuse_budget_guard": _gate(
            runtime_meta["preview_guard"]["policy_features"]["budget_refill_support"]
            and runtime_meta["preview_guard"]["persistent_policy_store"] == "database",
            "Preview family budgets are durable and refillable; short-window rate limits remain process-local.",
        ),
        "observability": _gate(
            observability["requests"]["requests_total"] >= 0
            and runtime_meta["observability_surface"]["endpoint"] == "/meta/observability",
            "Process-local request metrics and economy/housekeeping summary endpoint are available.",
        ),
        "recovery": _gate(
            runtime_meta["recovery_surface"]["snapshot_script"] == "scripts/export_world_snapshot.py"
            and runtime_meta["recovery_surface"]["repair_script"] == "scripts/repair_derived_state.py",
            "World snapshot export and derived-state repair tooling exist.",
        ),
        "contract_parity": _gate(
            runtime_meta["target_direction"]["rest_mcp_parity_target"] is True
            and runtime_meta["mcp_surface"]["tool_count"] >= 60,
            "REST/MCP parity target remains explicit and current MCP registry is exposed in metadata.",
        ),
        "admin_token_configured": _gate(
            bool(settings.CONTROL_PLANE_ADMIN_TOKEN),
            "CONTROL_PLANE_ADMIN_TOKEN is configured for admin policy operations.",
        ),
        "mcp_surface_enabled": _gate(
            bool(settings.MCP_SURFACE_ENABLED),
            "MCP surface is mounted in this runtime.",
        ),
        "housekeeping_active": _gate(
            latest_housekeeping is not None,
            "At least one housekeeping sweep has been recorded in this runtime.",
            blocker=False,
        ),
    }

    blocking_failures = sorted(
        gate_name for gate_name, gate in gates.items() if gate["blocker"] and not gate["ready"]
    )

    return {
        "local_preview_only": True,
        "public_rollout_ready": not blocking_failures,
        "blocking_failures": blocking_failures,
        "gates": gates,
    }
