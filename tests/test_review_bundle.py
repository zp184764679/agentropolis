"""Review-bundle and operator export tests."""

from __future__ import annotations

import asyncio
import json
import shutil
import uuid
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from agentropolis.models import Base
from agentropolis.services.seed import seed_game_data
from agentropolis.services.seed_world import seed_world
from scripts.build_review_bundle import build_review_bundle
from scripts.export_alert_snapshot import build_alert_export
from scripts.export_contract_snapshot import build_contract_snapshot
from scripts.export_execution_snapshot import build_execution_export
from scripts.export_observability_snapshot import build_observability_export
from scripts.export_rollout_readiness import build_rollout_readiness_export


def test_operator_bundle_surface_is_exposed_in_runtime_meta() -> None:
    meta = build_contract_snapshot()["runtime_meta"]
    assert meta["operator_bundle_surface"]["alerts_script"] == "scripts/export_alert_snapshot.py"
    assert meta["operator_bundle_surface"]["execution_script"] == "scripts/export_execution_snapshot.py"
    assert meta["operator_bundle_surface"]["observability_script"] == "scripts/export_observability_snapshot.py"
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
    assert "agentropolis execution-snapshot" in meta["operator_bundle_surface"]["cli_commands"]
    assert "agentropolis observability-snapshot" in meta["operator_bundle_surface"]["cli_commands"]
    assert "agentropolis build-review-bundle" in meta["operator_bundle_surface"]["cli_commands"]


def test_rollout_export_and_review_bundle_build_files() -> None:
    async def scenario() -> None:
        engine = create_async_engine(
            "sqlite+aiosqlite:///:memory:",
            echo=False,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with session_factory() as session:
            await seed_game_data(session)
            await seed_world(session)
            await session.commit()

        bundle_root = Path("tests/.tmp") / f"review-bundle-{uuid.uuid4().hex}"
        bundle_root.parent.mkdir(parents=True, exist_ok=True)
        try:
            readiness = await build_rollout_readiness_export(session_factory=session_factory)
            alerts = await build_alert_export(session_factory=session_factory)
            observability = await build_observability_export(session_factory=session_factory)
            execution = await build_execution_export(session_factory=session_factory)
            assert "rollout_readiness" in readiness
            assert "alerts" in alerts
            assert "observability" in observability
            assert "execution" in execution
            assert "mcp" in observability["observability"]
            assert "lag" in observability["observability"]["execution"]
            bundle = await build_review_bundle(bundle_root, session_factory=session_factory)
            summary_path = Path(bundle["output_dir"]) / "bundle-summary.json"
            contract_path = Path(bundle["artifacts"]["contract_snapshot"])
            readiness_path = Path(bundle["artifacts"]["rollout_readiness"])
            alerts_path = Path(bundle["artifacts"]["alerts"])
            observability_path = Path(bundle["artifacts"]["observability"])
            execution_path = Path(bundle["artifacts"]["execution"])
            world_path = Path(bundle["artifacts"]["world_snapshot"])
            gate_check_path = Path(bundle["artifacts"]["gate_check"])

            assert summary_path.exists()
            assert contract_path.exists()
            assert readiness_path.exists()
            assert alerts_path.exists()
            assert observability_path.exists()
            assert execution_path.exists()
            assert world_path.exists()
            assert gate_check_path.exists()

            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            assert summary["generated_at"]
            assert summary["git"]["commit"]
            assert isinstance(summary["git"]["dirty"], bool)
            assert summary["artifacts"]["contract_snapshot"].endswith("contract-snapshot.json")
            assert summary["artifacts"]["alerts"].endswith("alerts.json")
            assert summary["artifacts"]["observability"].endswith("observability.json")
            assert summary["artifacts"]["execution"].endswith("execution.json")
            gate_check = json.loads(gate_check_path.read_text(encoding="utf-8"))
            assert gate_check["tool_count"] >= 60
        finally:
            shutil.rmtree(bundle_root, ignore_errors=True)

        await engine.dispose()

    asyncio.run(scenario())
