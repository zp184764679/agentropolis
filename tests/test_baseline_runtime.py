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
    assert meta["preview_guard"]["policy_features"]["budget_refill_support"] is True
    assert meta["preview_guard"]["policy_features"]["audit_request_id_filtering"] is True
    assert meta["preview_guard"]["policy_features"]["stable_error_codes"] is True
    assert meta["preview_guard"]["policy_features"]["persistent_policy_store"] is True
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
    assert meta["request_context"]["request_id_header"] == "X-Agentropolis-Request-ID"
    assert "budget_refill" in meta["control_plane_surface"]["features"]
    assert "db_persisted_policy" in meta["control_plane_surface"]["features"]
    assert "audit_request_id_filtering" in meta["control_plane_surface"]["features"]
    assert "audit_request_context" in meta["control_plane_surface"]["features"]
    assert "stable_error_codes" in meta["control_plane_surface"]["features"]
    assert meta["orm_surface"]["target_models_registered"] is True
    assert meta["orm_surface"]["metadata_table_count"] >= 39
    assert meta["migration_surface"]["alembic_baseline_present"] is True
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
    assert meta["observability_surface"]["economy_health_snapshot"] is True
    assert meta["rollout_readiness_surface"]["endpoint"] == "/meta/rollout-readiness"
    assert meta["rollout_readiness_surface"]["contract_snapshot_script"] == "scripts/export_contract_snapshot.py"
    assert meta["rollout_readiness_surface"]["gate_check_script"] == "scripts/check_rollout_gate.py"
    assert "registry" in meta["economy_governance_surface"]["registry_snapshot"]
    assert meta["recovery_surface"]["snapshot_script"] == "scripts/export_world_snapshot.py"
    assert meta["recovery_surface"]["repair_script"] == "scripts/repair_derived_state.py"
    assert "agentropolis world-snapshot" in meta["recovery_surface"]["cli_commands"]


def test_sqlalchemy_mappers_and_metadata_create_on_sqlite() -> None:
    configure_mappers()

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    expected = {"agents", "regions", "strategy_profiles", "mercenary_contracts"}
    assert expected.issubset(Base.metadata.tables)
