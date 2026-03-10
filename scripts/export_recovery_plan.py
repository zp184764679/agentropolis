"""Export the current recovery plan to JSON."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from agentropolis.services.recovery_svc import build_recovery_plan


def build_recovery_plan_export() -> dict:
    return {"recovery_plan": build_recovery_plan()}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        default="openclaw/runtime/recovery-plan.json",
        help="Recovery-plan output path.",
    )
    args = parser.parse_args()
    payload = build_recovery_plan_export()
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
    print(target.as_posix())


if __name__ == "__main__":
    main()
