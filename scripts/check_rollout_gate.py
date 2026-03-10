"""Check local-preview rollout readiness from exported runtime/contract artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--readiness",
        default="openclaw/runtime/rollout-readiness.json",
        help="Path to a rollout-readiness JSON snapshot.",
    )
    parser.add_argument(
        "--contract-snapshot",
        default="openclaw/runtime/contract-snapshot.json",
        help="Path to a contract snapshot JSON file.",
    )
    args = parser.parse_args()

    readiness = json.loads(Path(args.readiness).read_text(encoding="utf-8"))
    contract_snapshot = json.loads(Path(args.contract_snapshot).read_text(encoding="utf-8"))

    summary = {
        "public_rollout_ready": readiness["public_rollout_ready"],
        "blocking_failures": readiness["blocking_failures"],
        "tool_count": contract_snapshot["mcp_registry"]["tool_count"],
        "transport": contract_snapshot["runtime_meta"]["mcp_surface"]["transport"],
    }
    print(json.dumps(summary, indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()
