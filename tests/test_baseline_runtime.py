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
    unmounted = {
        group["module"]: group["state"]
        for group in meta["rest_surface"]["unmounted_route_groups"]
    }

    assert meta["auth_surface"]["agent_auth"]["status"] == "migration_compatible"
    assert meta["orm_surface"]["target_models_registered"] is True
    assert meta["orm_surface"]["metadata_table_count"] >= 39
    assert meta["migration_surface"]["alembic_baseline_present"] is True
    assert mounted["agent"] == "preview_service_backed"
    assert mounted["transport"] == "preview_service_backed"
    assert unmounted["strategy"] == "importable_partially_implemented"


def test_sqlalchemy_mappers_and_metadata_create_on_sqlite() -> None:
    configure_mappers()

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    expected = {"agents", "regions", "strategy_profiles", "mercenary_contracts"}
    assert expected.issubset(Base.metadata.tables)
