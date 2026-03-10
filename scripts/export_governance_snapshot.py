"""Export the current economy governance snapshot to JSON."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from agentropolis.services.economy_governance import build_governance_snapshot


def build_governance_export() -> dict:
    return {"governance": build_governance_snapshot()}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        default="openclaw/runtime/governance.json",
        help="Governance snapshot output path.",
    )
    args = parser.parse_args()
    payload = build_governance_export()
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
    print(target.as_posix())


if __name__ == "__main__":
    main()
