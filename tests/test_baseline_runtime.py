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
    assert meta["preview_guard"]["rate_limit_store"] == "process_local_best_effort"
    assert meta["preview_guard"]["admin_api"]["path"] == "/meta/control-plane"
    assert meta["preview_guard"]["admin_api"]["error_code_header"] == "X-Agentropolis-Error-Code"
    assert meta["preview_guard"]["error_codes"]["control_plane_admin_invalid"] == (
        "Control-plane admin token is invalid."
    )
    assert meta["control_plane_surface"]["scope"] == "process_local_preview_policy"
    assert meta["control_plane_surface"]["error_code_header"] == "X-Agentropolis-Error-Code"
    assert meta["control_plane_surface"]["error_code_catalog"] == "preview_guard.error_codes"
    assert meta["request_context"]["request_id_header"] == "X-Agentropolis-Request-ID"
    assert "budget_refill" in meta["control_plane_surface"]["features"]
    assert "audit_request_id_filtering" in meta["control_plane_surface"]["features"]
    assert "audit_request_context" in meta["control_plane_surface"]["features"]
    assert "stable_error_codes" in meta["control_plane_surface"]["features"]
    assert meta["orm_surface"]["target_models_registered"] is True
    assert meta["orm_surface"]["metadata_table_count"] >= 39
    assert meta["migration_surface"]["alembic_baseline_present"] is True
    assert mounted["agent"] == "preview_service_backed"
    assert mounted["transport"] == "preview_service_backed"
    assert mounted["strategy"] == "preview_service_backed"
    assert mounted["warfare"] == "preview_service_backed"
    assert meta["rest_surface"]["unmounted_route_groups"] == []
    assert meta["rest_surface"]["error_code_header"] == "X-Agentropolis-Error-Code"


def test_sqlalchemy_mappers_and_metadata_create_on_sqlite() -> None:
    configure_mappers()

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    expected = {"agents", "regions", "strategy_profiles", "mercenary_contracts"}
    assert expected.issubset(Base.metadata.tables)
