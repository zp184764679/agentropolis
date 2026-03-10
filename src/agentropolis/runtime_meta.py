"""Machine-readable snapshot of the current runtime surface.

This module is intentionally simple and static for now. Its purpose is to expose
the current scaffold/runtime truth without forcing callers to infer behavior from
file presence alone.
"""

from __future__ import annotations

from agentropolis.control_contract import (
    CONTRACT_VERSION_HEADER,
    CONTROL_CONTRACT_VERSION,
    IDEMPOTENCY_KEY_HEADER,
)
from agentropolis.api.preview_guard import (
    ERROR_CODE_CATALOG,
    ERROR_CODE_HEADER,
)
from agentropolis.config import settings
from agentropolis.middleware import REQUEST_ID_HEADER
from agentropolis.models import Base
from agentropolis.services.concurrency import CONCURRENCY_ERROR_CODES
from agentropolis.services.economy_governance import build_governance_snapshot


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
        "reliable_endpoints": ["/health", "/meta/runtime", "/meta/contract"],
        "request_context": {
            "request_id_header": REQUEST_ID_HEADER,
            "client_fingerprint_source": "best_effort_request_client",
        },
        "public_contract_frozen": False,
        "control_contract_surface": {
            "endpoint": "/meta/contract",
            "minimum_contract_frozen": True,
            "version": CONTROL_CONTRACT_VERSION,
            "version_header": CONTRACT_VERSION_HEADER,
            "idempotency_key_header": IDEMPOTENCY_KEY_HEADER,
            "error_code_header": ERROR_CODE_HEADER,
            "request_id_header": REQUEST_ID_HEADER,
            "transport": "streamable-http",
            "scope_catalog_available": True,
            "error_taxonomy_available": True,
            "local_preview_only": True,
            "public_rollout_ready": False,
        },
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
        "concurrency_surface": {
            "enabled": True,
            "middleware": "RequestConcurrencyMiddleware",
            "authenticated_request_scope": "all",
            "entity_lock_scope": "writes_only",
            "actor_scopes": [
                "agent",
                "company",
                "admin",
            ],
            "max_concurrent": int(settings.CONCURRENCY_MAX_CONCURRENT),
            "housekeeping_reserved_slots": int(settings.HOUSEKEEPING_RESERVED_SLOTS),
            "request_slot_timeout_seconds": float(settings.CONCURRENCY_SLOT_TIMEOUT),
            "entity_lock_timeout_seconds": float(settings.CONCURRENCY_LOCK_TIMEOUT),
            "stripe_count": int(settings.CONCURRENCY_STRIPE_COUNT),
            "rate_limit_window_seconds": int(settings.RATE_LIMIT_WINDOW_SECONDS),
            "rate_limit_limits": {
                "agent": int(settings.RATE_LIMIT_AGENT_REQUESTS_PER_WINDOW),
                "company": int(settings.RATE_LIMIT_COMPANY_REQUESTS_PER_WINDOW),
                "admin": int(settings.RATE_LIMIT_ADMIN_REQUESTS_PER_WINDOW),
            },
            "error_codes": dict(CONCURRENCY_ERROR_CODES),
        },
        "alerts_surface": {
            "endpoint": "/meta/alerts",
            "export_script": "scripts/export_alert_snapshot.py",
            "sources": [
                "/meta/observability",
                "/meta/rollout-readiness",
            ],
        },
        "observability_surface": {
            "endpoint": "/meta/observability",
            "request_metrics": "process_local_best_effort",
            "economy_health_snapshot": True,
            "latest_housekeeping_summary": True,
            "concurrency_snapshot": True,
            "export_script": "scripts/export_observability_snapshot.py",
        },
        "rollout_readiness_surface": {
            "endpoint": "/meta/rollout-readiness",
            "contract_snapshot_script": "scripts/export_contract_snapshot.py",
            "gate_check_script": "scripts/check_rollout_gate.py",
            "runbooks": [
                "docs/local-preview-rollout.md",
                "docs/recovery-runbook.md",
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
        "prompt_surface": {
            "agent_brain_prompt": "prompts/agent-brain.md",
            "format": "markdown_system_prompt",
            "decision_framework": [
                "survival_first",
                "company_solvent_before_expansion",
                "goals_before_side_quests",
                "mcp_first_rest_fallback_mounted_only",
                "respect_error_codes_and_preview_policy",
            ],
        },
        "openclaw_surface": {
            "local_preview_only": True,
            "public_rollout_ready": False,
            "prompt_file": "prompts/agent-brain.md",
            "skill_file": "skills/agentropolis-world/SKILL.md",
            "transport": "streamable-http",
            "config_templates": [
                "openclaw/agent-template.yaml",
                "openclaw/fleet-template.yaml",
                "openclaw/bootstrap.example.env",
            ],
            "compose_file": "docker-compose.multi-agent.yml",
            "registration_script": "scripts/register_agents.py",
            "monitor_script": "scripts/monitor_agents.py",
            "manifest_output_default": "openclaw/runtime/agents.json",
        },
        "economy_governance_surface": {
            "registry_snapshot": build_governance_snapshot(),
            "staged_rollout_flags": [
                "PREVIEW_SURFACE_ENABLED",
                "PREVIEW_DEGRADED_MODE",
                "MCP_SURFACE_ENABLED",
            ],
        },
        "recovery_surface": {
            "snapshot_script": "scripts/export_world_snapshot.py",
            "repair_script": "scripts/repair_derived_state.py",
            "cli_commands": [
                "agentropolis world-snapshot",
                "agentropolis repair-derived-state",
            ],
            "local_preview_runbook": "openclaw/README.md",
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
            "concurrency_guard",
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
        "operator_bundle_surface": {
            "alerts_script": "scripts/export_alert_snapshot.py",
            "observability_script": "scripts/export_observability_snapshot.py",
            "rollout_readiness_script": "scripts/export_rollout_readiness.py",
            "review_bundle_script": "scripts/build_review_bundle.py",
            "gate_check_script": "scripts/check_rollout_gate.py",
            "contract_catalog_script": "scripts/export_contract_snapshot.py",
            "summary_metadata": [
                "generated_at",
                "git.branch",
                "git.commit",
                "git.dirty",
            ],
            "cli_commands": [
                "agentropolis contract-snapshot",
                "agentropolis check-rollout-gate",
                "agentropolis alerts-snapshot",
                "agentropolis observability-snapshot",
                "agentropolis rollout-readiness",
                "agentropolis build-review-bundle",
            ],
        },
    }
