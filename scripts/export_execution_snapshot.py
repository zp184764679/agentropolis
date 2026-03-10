"""Export local-preview execution semantics snapshot to JSON."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Callable

from agentropolis.database import async_session
from agentropolis.services.execution_svc import build_execution_snapshot


SessionFactory = Callable[[], object]


async def build_execution_export(*, session_factory: SessionFactory | None = None) -> dict:
    factory = session_factory or async_session
    async with factory() as session:
        payload = await build_execution_snapshot(session)
    return {"execution": payload}


async def _run(output_path: str, *, session_factory: SessionFactory | None = None) -> Path:
    payload = await build_execution_export(session_factory=session_factory)
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        default="openclaw/runtime/execution.json",
        help="Execution snapshot output path.",
    )
    args = parser.parse_args()
    output = asyncio.run(_run(args.output))
    print(output.as_posix())


if __name__ == "__main__":
    main()
