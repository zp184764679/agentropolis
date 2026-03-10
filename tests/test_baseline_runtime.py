"""Smoke tests for the migration baseline."""

from sqlalchemy import create_engine
from sqlalchemy.orm import configure_mappers

from agentropolis.models import Base
from agentropolis.runtime_meta import build_runtime_metadata


def test_runtime_metadata_reports_target_registry() -> None:
    meta = build_runtime_metadata()
    mounted = {
        group["module"]: group["state"]
        for group in meta["rest_surface"]["mounted_route_groups"]
    }

    assert meta["auth_surface"]["agent_auth"]["status"] == "migration_compatible"
    assert meta["preview_guard"]["surface_enabled"] is True
    assert meta["preview_guard"]["writes_enabled"] is True
    assert meta["preview_guard"]["degraded_mode"] is False
    assert meta["preview_guard"]["agent_policy_count"] == 0
    assert meta["preview_guard"]["audit_log_size"] == 0
    assert meta["preview_guard"]["policy_features"]["authenticated_read_policy"] == "family_scoped"
    assert (
        meta["preview_guard"]["policy_features"]["authenticated_write_policy"]
        == "family_scoped_with_budget_and_operation_policy"
    )
    assert meta["preview_guard"]["policy_features"]["budget_refill_support"] is True
    assert meta["preview_guard"]["policy_features"]["per_operation_budget_support"] is True
    assert meta["preview_guard"]["policy_features"]["unsafe_operation_denylist"] is True
    assert meta["preview_guard"]["policy_features"]["spending_cap_support"] is True
    assert meta["preview_guard"]["policy_features"]["audit_request_id_filtering"] is True
    assert meta["preview_guard"]["policy_features"]["stable_error_codes"] is True
    assert meta["preview_guard"]["policy_features"]["persistent_policy_store"] is True
    assert "place_buy_order" in meta["preview_guard"]["dangerous_operations"]
    assert meta["preview_guard"]["rate_limit_store"] == "process_local_best_effort"
    assert meta["preview_guard"]["persistent_policy_store"] == "database"
    assert meta["preview_guard"]["admin_api"]["path"] == "/meta/control-plane"
    assert meta["preview_guard"]["admin_api"]["error_code_header"] == "X-Agentropolis-Error-Code"
    assert meta["preview_guard"]["error_codes"]["control_plane_admin_invalid"] == (
        "Control-plane admin token is invalid."
    )
    assert meta["control_plane_surface"]["scope"] == "db_persisted_preview_policy"
    assert meta["control_plane_surface"]["persistent"] is True
    assert meta["control_plane_surface"]["error_code_header"] == "X-Agentropolis-Error-Code"
    assert meta["control_plane_surface"]["error_code_catalog"] == "preview_guard.error_codes"
    assert meta["concurrency_surface"]["enabled"] is True
    assert meta["concurrency_surface"]["middleware"] == "RequestConcurrencyMiddleware"
    assert meta["concurrency_surface"]["authenticated_request_scope"] == "all"
    assert meta["concurrency_surface"]["entity_lock_scope"] == "writes_only"
    assert meta["concurrency_surface"]["actor_scopes"] == ["agent", "company", "admin"]
    assert meta["concurrency_surface"]["housekeeping_reserved_slots"] == 5
    assert meta["concurrency_surface"]["max_concurrent"] == 25
    assert meta["concurrency_surface"]["stripe_count"] == 256
    assert meta["concurrency_surface"]["rate_limit_limits"]["agent"] == 120
    assert meta["concurrency_surface"]["rate_limit_limits"]["company"] == 120
    assert meta["concurrency_surface"]["rate_limit_limits"]["admin"] == 60
    assert meta["concurrency_surface"]["error_codes"]["concurrency_rate_limited"] == (
        "Authenticated request rate limit exceeded."
    )
    assert meta["request_context"]["request_id_header"] == "X-Agentropolis-Request-ID"
    assert meta["control_contract_surface"]["endpoint"] == "/meta/contract"
    assert meta["control_contract_surface"]["minimum_contract_frozen"] is True
    assert meta["control_contract_surface"]["version"] == "2026-03-preview.3"
    assert meta["control_contract_surface"]["version_header"] == "X-Agentropolis-Contract-Version"
    assert meta["control_contract_surface"]["idempotency_key_header"] == "X-Idempotency-Key"
    assert meta["control_contract_surface"]["scope_catalog_available"] is True
    assert meta["control_contract_surface"]["error_taxonomy_available"] is True
    assert "budget_refill" in meta["control_plane_surface"]["features"]
    assert "per_operation_budgets" in meta["control_plane_surface"]["features"]
    assert "unsafe_operation_denylists" in meta["control_plane_surface"]["features"]
    assert "spending_caps" in meta["control_plane_surface"]["features"]
    assert "db_persisted_policy" in meta["control_plane_surface"]["features"]
    assert "audit_request_id_filtering" in meta["control_plane_surface"]["features"]
    assert "audit_request_context" in meta["control_plane_surface"]["features"]
    assert "stable_error_codes" in meta["control_plane_surface"]["features"]
    assert meta["orm_surface"]["target_models_registered"] is True
    assert meta["orm_surface"]["metadata_table_count"] >= 39
    assert meta["migration_surface"]["alembic_baseline_present"] is True
    assert "/meta/contract" in meta["reliable_endpoints"]
    assert mounted["agent"] == "preview_service_backed"
    assert mounted["production"] == "service_backed_writes"
    assert mounted["company"] == "mixed_agent_creation_legacy_company_ops"
    assert mounted["transport"] == "preview_service_backed"
    assert mounted["strategy"] == "preview_service_backed"
    assert mounted["warfare"] == "preview_service_backed"
    assert mounted["autonomy"] == "preview_service_backed"
    assert mounted["digest"] == "preview_service_backed"
    assert mounted["dashboard"] == "preview_service_backed"
    assert mounted["intel"] == "preview_service_backed"
    assert meta["rest_surface"]["unmounted_route_groups"] == []
    assert meta["rest_surface"]["validation_error_status"] == 422
    assert meta["rest_surface"]["error_code_header"] == "X-Agentropolis-Error-Code"
    assert meta["mcp_surface"]["transport"] == "streamable-http"
    assert meta["mcp_surface"]["transport_frozen"] is True
    assert meta["mcp_surface"]["local_preview_only"] is True
    assert meta["mcp_surface"]["public_rollout_ready"] is False
    assert meta["mcp_surface"]["tool_count"] == 60
    assert meta["mcp_surface"]["tool_groups"]["agent"] == 6
    assert meta["mcp_surface"]["tool_groups"]["company"] == 4
    assert meta["mcp_surface"]["tool_groups"]["market"] == 8
    assert meta["mcp_surface"]["tool_groups"]["strategy"] == 4
    assert meta["mcp_surface"]["tool_groups"]["social"] == 7
    assert meta["mcp_surface"]["tool_groups"]["warfare"] == 4
    assert meta["mcp_surface"]["mcp_only_local_preview_groups"] == ["notifications", "npc"]
    assert meta["prompt_surface"]["agent_brain_prompt"] == "prompts/agent-brain.md"
    assert "survival_first" in meta["prompt_surface"]["decision_framework"]
    assert meta["openclaw_surface"]["local_preview_only"] is True
    assert meta["openclaw_surface"]["public_rollout_ready"] is False
    assert meta["openclaw_surface"]["transport"] == "streamable-http"
    assert meta["openclaw_surface"]["compose_file"] == "docker-compose.multi-agent.yml"
    assert meta["openclaw_surface"]["registration_script"] == "scripts/register_agents.py"
    assert meta["openclaw_surface"]["monitor_script"] == "scripts/monitor_agents.py"
    assert meta["openclaw_surface"]["manifest_output_default"] == "openclaw/runtime/agents.json"
    assert meta["observability_surface"]["endpoint"] == "/meta/observability"
    assert meta["observability_surface"]["request_metrics"] == "process_local_best_effort"
    assert meta["observability_surface"]["mcp_metrics_snapshot"] is True
    assert meta["observability_surface"]["economy_health_snapshot"] is True
    assert meta["observability_surface"]["agent_behavior_snapshot"] is True
    assert meta["observability_surface"]["concurrency_snapshot"] is True
    assert meta["observability_surface"]["preview_policy_snapshot"] is True
    assert meta["observability_surface"]["execution_lag_snapshot"] is True
    assert "request_complete" in meta["observability_surface"]["structured_logs"]
    assert "mcp_tool_call" in meta["observability_surface"]["structured_logs"]
    assert "housekeeping_sweep_completed" in meta["observability_surface"]["structured_logs"]
    assert meta["observability_surface"]["thresholds"]["slow_request_ms"] == 250
    assert meta["observability_surface"]["thresholds"]["slow_mcp_ms"] == 250
    assert meta["observability_surface"]["thresholds"]["execution_lag_warning_seconds"] == 120
    assert meta["observability_surface"]["thresholds"]["execution_lag_critical_seconds"] == 300
    assert meta["observability_surface"]["thresholds"]["request_error_warning_rate"] == 0.25
    assert meta["observability_surface"]["thresholds"]["mcp_failure_warning_rate"] == 0.25
    assert meta["observability_surface"]["export_script"] == "scripts/export_observability_snapshot.py"
    assert meta["execution_surface"]["endpoint"] == "/meta/execution"
    assert meta["execution_surface"]["job_states"] == [
        "accepted",
        "pending",
        "running",
        "completed",
        "failed",
        "dead_letter",
    ]
    assert meta["execution_surface"]["job_types"] == [
        "housekeeping_backfill",
        "derived_state_repair",
    ]
    assert meta["execution_surface"]["phase_contract"]["max_attempts"] == 2
    assert meta["execution_surface"]["retry_policy"]["default_max_attempts"] == 3
    assert meta["execution_surface"]["backfill_policy"]["auto_gap_detection"] is True
    assert meta["execution_surface"]["export_script"] == "scripts/export_execution_snapshot.py"
    assert meta["alerts_surface"]["endpoint"] == "/meta/alerts"
    assert meta["alerts_surface"]["export_script"] == "scripts/export_alert_snapshot.py"
    assert meta["alerts_surface"]["sources"] == ["/meta/observability", "/meta/rollout-readiness"]
    assert meta["rollout_readiness_surface"]["endpoint"] == "/meta/rollout-readiness"
    assert meta["rollout_readiness_surface"]["contract_snapshot_script"] == "scripts/export_contract_snapshot.py"
    assert meta["rollout_readiness_surface"]["gate_check_script"] == "scripts/check_rollout_gate.py"
    assert "docs/execution-model.md" in meta["rollout_readiness_surface"]["runbooks"]
    assert meta["operator_bundle_surface"]["alerts_script"] == "scripts/export_alert_snapshot.py"
    assert meta["operator_bundle_surface"]["execution_script"] == "scripts/export_execution_snapshot.py"
    assert meta["operator_bundle_surface"]["governance_script"] == "scripts/export_governance_snapshot.py"
    assert meta["operator_bundle_surface"]["observability_script"] == "scripts/export_observability_snapshot.py"
    assert meta["operator_bundle_surface"]["recovery_plan_script"] == "scripts/export_recovery_plan.py"
    assert meta["operator_bundle_surface"]["rollout_readiness_script"] == "scripts/export_rollout_readiness.py"
    assert meta["operator_bundle_surface"]["review_bundle_script"] == "scripts/build_review_bundle.py"
    assert meta["operator_bundle_surface"]["gate_check_script"] == "scripts/check_rollout_gate.py"
    assert meta["operator_bundle_surface"]["summary_metadata"] == [
        "generated_at",
        "git.branch",
        "git.commit",
        "git.dirty",
    ]
    assert "agentropolis check-rollout-gate" in meta["operator_bundle_surface"]["cli_commands"]
    assert "agentropolis alerts-snapshot" in meta["operator_bundle_surface"]["cli_commands"]
    assert "agentropolis execution-snapshot" in meta["operator_bundle_surface"]["cli_commands"]
    assert "agentropolis observability-snapshot" in meta["operator_bundle_surface"]["cli_commands"]
    assert "registry" in meta["economy_governance_surface"]["registry_snapshot"]
    assert "staged_rollout_flags" in meta["economy_governance_surface"]["registry_snapshot"]
    assert "ownership_index" in meta["economy_governance_surface"]["registry_snapshot"]
    assert meta["economy_governance_surface"]["staged_rollout_flags"][:2] == [
        "ECONOMY_BALANCE_PROFILE",
        "ECONOMY_DYNAMIC_PRICING_STAGE",
    ]
    assert meta["economy_governance_surface"]["export_script"] == "scripts/export_governance_snapshot.py"
    assert "agentropolis governance-snapshot" in meta["economy_governance_surface"]["cli_commands"]
    assert meta["recovery_surface"]["snapshot_script"] == "scripts/export_world_snapshot.py"
    assert meta["recovery_surface"]["repair_script"] == "scripts/repair_derived_state.py"
    assert meta["recovery_surface"]["replay_script"] == "scripts/replay_housekeeping.py"
    assert meta["recovery_surface"]["plan_script"] == "scripts/export_recovery_plan.py"
    assert meta["recovery_surface"]["recovery_strategy"] == "snapshot_replay_repair"
    assert meta["recovery_surface"]["migration_safety_doc"] == "docs/recovery-runbook.md"
    assert "agentropolis recovery-plan" in meta["recovery_surface"]["cli_commands"]
    assert "agentropolis replay-housekeeping" in meta["recovery_surface"]["cli_commands"]
    assert "agentropolis world-snapshot" in meta["recovery_surface"]["cli_commands"]
    assert "concurrency_guard" in meta["external_rollout_gates"]
    assert "execution_semantics" in meta["external_rollout_gates"]


def test_sqlalchemy_mappers_and_metadata_create_on_sqlite() -> None:
    configure_mappers()

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    expected = {"agents", "regions", "strategy_profiles", "mercenary_contracts"}
    assert expected.issubset(Base.metadata.tables)
