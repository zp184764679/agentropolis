"""Export a machine-readable contract snapshot for local-preview review."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from agentropolis.runtime_meta import build_runtime_metadata
from agentropolis.mcp.server import mcp


def build_contract_snapshot() -> dict:
    meta = build_runtime_metadata()
    tool_names = sorted(mcp._tool_manager._tools.keys())
    return {
        "runtime_meta": meta,
        "mcp_registry": {
            "tool_count": len(tool_names),
            "tool_names": tool_names,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        default="openclaw/runtime/contract-snapshot.json",
        help="Snapshot output path.",
    )
    args = parser.parse_args()
    snapshot = build_contract_snapshot()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(snapshot, indent=2, ensure_ascii=True), encoding="utf-8")
    print(output.as_posix())


if __name__ == "__main__":
    main()
