"""Export a world snapshot for local-preview recovery drills."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from agentropolis.database import async_session
from agentropolis.services.recovery_svc import build_world_snapshot


async def _run(output_path: str, housekeeping_limit: int) -> Path:
    async with async_session() as session:
        snapshot = await build_world_snapshot(session, housekeeping_limit=housekeeping_limit)
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(snapshot, indent=2, ensure_ascii=True), encoding="utf-8")
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        default="openclaw/runtime/world-snapshot.json",
        help="Snapshot output path.",
    )
    parser.add_argument(
        "--housekeeping-limit",
        type=int,
        default=5,
        help="Number of recent housekeeping rows to include.",
    )
    args = parser.parse_args()
    output = asyncio.run(_run(args.output, args.housekeeping_limit))
    print(output.as_posix())


if __name__ == "__main__":
    main()
