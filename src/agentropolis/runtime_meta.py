"""Machine-readable snapshot of the current runtime surface.

This module is intentionally simple and static for now. Its purpose is to expose
the current scaffold/runtime truth without forcing callers to infer behavior from
file presence alone.
"""

from __future__ import annotations


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
        "state": "stubbed",
        "auth_model": "target_agent_auth",
    },
    {
        "module": "world",
        "prefix": "/api/world",
        "state": "stubbed",
        "auth_model": "target_agent_auth",
    },
    {
        "module": "skills",
        "prefix": "/api/skills",
        "state": "stubbed",
        "auth_model": "target_agent_auth",
    },
    {
        "module": "guild",
        "prefix": "/api/guild",
        "state": "stubbed",
        "auth_model": "target_agent_auth",
    },
    {
        "module": "diplomacy",
        "prefix": "/api/diplomacy",
        "state": "stubbed",
        "auth_model": "target_agent_auth",
    },
    {
        "module": "transport",
        "prefix": "/api/transport",
        "state": "stubbed",
        "auth_model": "target_agent_auth",
    },
    {
        "module": "strategy",
        "prefix": "/api/strategy",
        "state": "partially_implemented",
        "auth_model": "target_agent_auth",
    },
    {
        "module": "decisions",
        "prefix": "/api/agent/decisions",
        "state": "partially_implemented",
        "auth_model": "target_agent_auth",
    },
    {
        "module": "warfare",
        "prefix": "/api/warfare",
        "state": "partially_implemented",
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
                "status": "migration_stub",
                "entrypoint": "get_current_agent",
            },
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
