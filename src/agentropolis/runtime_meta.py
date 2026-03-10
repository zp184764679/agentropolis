"""Machine-readable snapshot of the current runtime surface.

This module is intentionally simple and static for now. Its purpose is to expose
the current scaffold/runtime truth without forcing callers to infer behavior from
file presence alone.
"""

from __future__ import annotations

from agentropolis.api.preview_guard import (
    ERROR_CODE_CATALOG,
    ERROR_CODE_HEADER,
)
from agentropolis.config import settings
from agentropolis.middleware import REQUEST_ID_HEADER
from agentropolis.models import Base


MOUNTED_ROUTE_GROUPS = [
    {
        "module": "market",
        "prefix": "/api/market",
        "state": "mixed_scaffold_reads",
        "auth_model": "legacy_company_auth",
    },
    {
        "module": "production",
        "prefix": "/api/production",
        "state": "service_backed_writes",
        "auth_model": "legacy_company_auth",
    },
    {
        "module": "inventory",
        "prefix": "/api/inventory",
        "state": "mixed_scaffold_reads",
        "auth_model": "legacy_company_auth",
    },
    {
        "module": "company",
        "prefix": "/api/company",
        "state": "mixed_agent_creation_legacy_company_ops",
        "auth_model": "mixed_agent_company_auth",
    },
    {
        "module": "game",
        "prefix": "/api/game",
        "state": "mixed_scaffold_reads",
        "auth_model": "mixed_legacy",
    },
    {
        "module": "agent",
        "prefix": "/api/agent",
        "state": "preview_service_backed",
        "auth_model": "target_agent_auth",
    },
    {
        "module": "world",
        "prefix": "/api/world",
        "state": "preview_service_backed",
        "auth_model": "target_agent_auth",
    },
    {
        "module": "skills",
        "prefix": "/api/skills",
        "state": "preview_service_backed",
        "auth_model": "target_agent_auth",
    },
    {
        "module": "transport",
        "prefix": "/api/transport",
        "state": "preview_service_backed",
        "auth_model": "target_agent_auth",
    },
    {
        "module": "guild",
        "prefix": "/api/guild",
        "state": "preview_service_backed",
        "auth_model": "target_agent_auth",
    },
    {
        "module": "diplomacy",
        "prefix": "/api/diplomacy",
        "state": "preview_service_backed",
        "auth_model": "target_agent_auth",
    },
    {
        "module": "strategy",
        "prefix": "/api/strategy",
        "state": "preview_service_backed",
        "auth_model": "target_agent_auth",
    },
    {
        "module": "decisions",
        "prefix": "/api/agent/decisions",
        "state": "preview_service_backed",
        "auth_model": "target_agent_auth",
    },
    {
        "module": "warfare",
        "prefix": "/api/warfare",
        "state": "preview_service_backed",
        "auth_model": "target_agent_auth",
    },
    {
        "module": "autonomy",
        "prefix": "/api/autonomy",
        "state": "preview_service_backed",
        "auth_model": "target_agent_auth",
    },
    {
        "module": "digest",
        "prefix": "/api/digest",
        "state": "preview_service_backed",
        "auth_model": "target_agent_auth",
    },
    {
        "module": "dashboard",
        "prefix": "/api/dashboard",
        "state": "preview_service_backed",
        "auth_model": "target_agent_auth",
    },
    {
        "module": "intel",
        "prefix": "/api/intel",
        "state": "preview_service_backed",
        "auth_model": "target_agent_auth",
    },
]

UNMOUNTED_ROUTE_GROUPS = []

def build_runtime_metadata(*, preview_guard_state: dict | None = None) -> dict:
    """Return a machine-readable snapshot of the current runtime surface."""
    return {
        "stage": "migration_scaffold",
        "reliable_endpoints": ["/health", "/meta/runtime"],
        "request_context": {
            "request_id_header": REQUEST_ID_HEADER,
            "client_fingerprint_source": "best_effort_request_client",
        },
        "public_contract_frozen": False,
        "control_plane_surface": {
            "admin_endpoint": "/meta/control-plane",
            "scope": "db_persisted_preview_policy",
            "persistent": True,
            "request_id_header": REQUEST_ID_HEADER,
            "error_code_header": ERROR_CODE_HEADER,
            "error_code_catalog": "preview_guard.error_codes",
            "features": [
                "runtime_policy_toggles",
                "per_agent_family_authz",
                "per_family_budgets",
                "budget_refill",
                "audit_log_filtering",
                "audit_request_id_filtering",
                "audit_request_context",
                "stable_error_codes",
                "db_persisted_policy",
            ],
        },
        "auth_surface": {
            "company_auth": {
                "status": "active_legacy",
                "entrypoint": "get_current_company",
            },
            "agent_auth": {
                "status": "migration_compatible",
                "entrypoint": "get_current_agent",
            },
        },
        "preview_guard": preview_guard_state
        or {
            "surface_enabled": True,
            "writes_enabled": True,
            "warfare_mutations_enabled": True,
            "degraded_mode": False,
            "mutation_window_seconds": 60,
            "agent_mutations_per_window": 60,
            "registrations_per_window_per_host": 10,
            "family_limits": {},
            "agent_policy_count": 0,
            "audit_log_size": 0,
            "policy_features": {
                "authenticated_read_policy": "family_scoped",
                "authenticated_write_policy": "family_scoped_with_budget",
                "public_preview_read_policy": "surface_only",
                "admin_action_context": "structured_reason_note",
                "budget_refill_support": True,
                "audit_filter_support": True,
                "audit_request_id_filtering": True,
                "stable_error_codes": True,
                "persistent_policy_store": True,
            },
            "rate_limit_store": "process_local_best_effort",
            "persistent_policy_store": "database",
            "error_codes": dict(ERROR_CODE_CATALOG),
            "admin_api": {
                "path": "/meta/control-plane",
                "configured": False,
                "token_header": "X-Control-Plane-Token",
                "request_id_header": REQUEST_ID_HEADER,
                "error_code_header": ERROR_CODE_HEADER,
            },
        },
        "orm_surface": {
            "metadata_table_count": len(Base.metadata.tables),
            "target_models_registered": True,
            "mapper_graph_state": "configured_in_tests",
        },
        "rest_surface": {
            "mounted_route_groups": MOUNTED_ROUTE_GROUPS,
            "unmounted_route_groups": UNMOUNTED_ROUTE_GROUPS,
            "placeholder_error_status": 501,
            "validation_error_status": 422,
            "error_code_header": ERROR_CODE_HEADER,
        },
        "mcp_surface": {
            "mounted": bool(settings.MCP_SURFACE_ENABLED),
            "mount_path": "/mcp",
            "transport": "streamable-http",
            "transport_frozen": True,
            "local_preview_only": True,
            "public_rollout_ready": False,
            "tool_count": 60,
            "tool_groups": {
                "agent": 6,
                "company": 4,
                "intel": 5,
                "inventory": 3,
                "market": 8,
                "notifications": 2,
                "npc": 2,
                "production": 5,
                "skills": 2,
                "social": 7,
                "strategy": 4,
                "transport": 3,
                "warfare": 4,
                "world": 5,
            },
            "mcp_only_local_preview_groups": [
                "notifications",
                "npc",
            ],
        },
        "migration_surface": {
            "alembic_baseline_present": True,
            "fresh_db_bootstrap": "alembic_then_seed_game_data_then_seed_world",
        },
        "target_direction": {
            "auth_model": "agent_based",
            "world_model": "real_time_housekeeping_lazy_settlement",
            "rest_mcp_parity_target": True,
        },
        "external_rollout_gates": [
            "control_contract",
            "authz",
            "abuse_budget_guard",
            "observability",
            "recovery",
            "contract_parity",
        ],
        "doc_sources": [
            "README.md",
            "PLAN.md",
            "CLAUDE.md",
            ".github/README.md",
        ],
    }
