"""Build a local-preview review bundle from current runtime artifacts."""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable

from scripts.check_rollout_gate import build_rollout_gate_summary
from scripts.export_alert_snapshot import build_alert_export
from scripts.export_contract_snapshot import build_contract_snapshot
from scripts.export_observability_snapshot import build_observability_export
from scripts.export_rollout_readiness import build_rollout_readiness_export
from scripts.export_world_snapshot import _run as export_world_snapshot_run


SessionFactory = Callable[[], object]


def _build_git_metadata() -> dict:
    repo_root = Path(__file__).resolve().parent.parent

    def _run_git(*args: str) -> str | None:
        completed = subprocess.run(
            ["git", *args],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            return None
        return completed.stdout.strip()

    commit = _run_git("rev-parse", "--short", "HEAD")
    branch = _run_git("branch", "--show-current")
    dirty_output = _run_git("status", "--porcelain")
    return {
        "branch": branch or "unknown",
        "commit": commit or "unknown",
        "dirty": bool(dirty_output),
    }


async def build_review_bundle(
    output_dir: str | Path,
    *,
    housekeeping_limit: int = 5,
    session_factory: SessionFactory | None = None,
) -> dict:
    target_dir = Path(output_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    contract_snapshot = build_contract_snapshot()
    contract_path = target_dir / "contract-snapshot.json"
    contract_path.write_text(
        json.dumps(contract_snapshot, indent=2, ensure_ascii=True),
        encoding="utf-8",
    )

    readiness_payload = await build_rollout_readiness_export(session_factory=session_factory)
    readiness_path = target_dir / "rollout-readiness.json"
    readiness_path.write_text(
        json.dumps(readiness_payload, indent=2, ensure_ascii=True),
        encoding="utf-8",
    )

    observability_payload = await build_observability_export(session_factory=session_factory)
    observability_path = target_dir / "observability.json"
    observability_path.write_text(
        json.dumps(observability_payload, indent=2, ensure_ascii=True),
        encoding="utf-8",
    )

    alerts_payload = await build_alert_export(session_factory=session_factory)
    alerts_path = target_dir / "alerts.json"
    alerts_path.write_text(
        json.dumps(alerts_payload, indent=2, ensure_ascii=True),
        encoding="utf-8",
    )

    world_snapshot_path = await export_world_snapshot_run(
        str(target_dir / "world-snapshot.json"),
        housekeeping_limit,
        session_factory=session_factory,
    )

    gate_summary = build_rollout_gate_summary(
        readiness_payload["rollout_readiness"],
        contract_snapshot,
    )
    gate_summary_path = target_dir / "gate-check.json"
    gate_summary_path.write_text(
        json.dumps(gate_summary, indent=2, ensure_ascii=True),
        encoding="utf-8",
    )

    manifest_path = Path("openclaw/runtime/agents.json")
    bundle = {
        "output_dir": target_dir.as_posix(),
        "generated_at": datetime.now(UTC).isoformat(),
        "git": _build_git_metadata(),
        "artifacts": {
            "contract_snapshot": contract_path.as_posix(),
            "rollout_readiness": readiness_path.as_posix(),
            "observability": observability_path.as_posix(),
            "alerts": alerts_path.as_posix(),
            "world_snapshot": world_snapshot_path.as_posix(),
            "gate_check": gate_summary_path.as_posix(),
            "manifest_present": manifest_path.exists(),
        },
    }
    summary_path = target_dir / "bundle-summary.json"
    summary_path.write_text(json.dumps(bundle, indent=2, ensure_ascii=True), encoding="utf-8")
    return bundle


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        default="openclaw/runtime/review-bundle",
        help="Bundle output directory.",
    )
    parser.add_argument(
        "--housekeeping-limit",
        type=int,
        default=5,
        help="Number of housekeeping rows to include in the world snapshot.",
    )
    args = parser.parse_args()
    bundle = asyncio.run(
        build_review_bundle(
            args.output_dir,
            housekeeping_limit=args.housekeeping_limit,
        )
    )
    print(json.dumps(bundle, indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()
