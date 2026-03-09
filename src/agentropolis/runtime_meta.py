"""Machine-readable snapshot of the current runtime surface.

This module is intentionally simple and static for now. Its purpose is to expose
the current scaffold/runtime truth without forcing callers to infer behavior from
file presence alone.
"""

from __future__ import annotations

from agentropolis.models import Base


MOUNTED_ROUTE_GROUPS = [
    {
        "module": "market",
        "prefix": "/api/market",
        "state": "placeholder-heavy",
        "auth_model": "legacy_company_auth",
    },
    {
        "module": "production",
        "prefix": "/api/production",
        "state": "placeholder-heavy",
        "auth_model": "legacy_company_auth",
    },
    {
        "module": "inventory",
        "prefix": "/api/inventory",
        "state": "placeholder-heavy",
        "auth_model": "legacy_company_auth",
    },
    {
        "module": "company",
        "prefix": "/api/company",
        "state": "placeholder-heavy",
        "auth_model": "legacy_company_auth",
    },
    {
        "module": "game",
        "prefix": "/api/game",
        "state": "placeholder-heavy",
        "auth_model": "mixed_legacy",
    },
]

UNMOUNTED_ROUTE_GROUPS = [
    {
        "module": "agent",
        "prefix": "/api/agent",
        "state": "importable_service_backed_unmounted",
        "auth_model": "target_agent_auth",
    },
    {
        "module": "world",
        "prefix": "/api/world",
        "state": "importable_service_backed_unmounted",
        "auth_model": "target_agent_auth",
    },
    {
        "module": "skills",
        "prefix": "/api/skills",
        "state": "importable_service_backed_unmounted",
        "auth_model": "target_agent_auth",
    },
    {
        "module": "guild",
        "prefix": "/api/guild",
        "state": "importable_stubbed",
        "auth_model": "target_agent_auth",
    },
    {
        "module": "diplomacy",
        "prefix": "/api/diplomacy",
        "state": "importable_stubbed",
        "auth_model": "target_agent_auth",
    },
    {
        "module": "transport",
        "prefix": "/api/transport",
        "state": "importable_service_backed_unmounted",
        "auth_model": "target_agent_auth",
    },
    {
        "module": "strategy",
        "prefix": "/api/strategy",
        "state": "importable_partially_implemented",
        "auth_model": "target_agent_auth",
    },
    {
        "module": "decisions",
        "prefix": "/api/agent/decisions",
        "state": "importable_partially_implemented",
        "auth_model": "target_agent_auth",
    },
    {
        "module": "warfare",
        "prefix": "/api/warfare",
        "state": "importable_partially_implemented",
        "auth_model": "target_agent_auth",
    },
]


def build_runtime_metadata() -> dict:
    """Return a machine-readable snapshot of the current runtime surface."""
    return {
        "stage": "migration_scaffold",
        "reliable_endpoints": ["/health", "/meta/runtime"],
        "public_contract_frozen": False,
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
        "orm_surface": {
            "metadata_table_count": len(Base.metadata.tables),
            "target_models_registered": True,
            "mapper_graph_state": "configured_in_tests",
        },
        "rest_surface": {
            "mounted_route_groups": MOUNTED_ROUTE_GROUPS,
            "unmounted_route_groups": UNMOUNTED_ROUTE_GROUPS,
            "placeholder_error_status": 501,
        },
        "mcp_surface": {
            "mounted": False,
            "transport_frozen": False,
            "public_rollout_ready": False,
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
