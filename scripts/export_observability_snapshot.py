"""Export local-preview observability to JSON."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Callable

from agentropolis.database import async_session
from agentropolis.services.observability_svc import build_observability_snapshot


SessionFactory = Callable[[], object]


async def build_observability_export(*, session_factory: SessionFactory | None = None) -> dict:
    factory = session_factory or async_session
    async with factory() as session:
        observability = await build_observability_snapshot(session)
    return {"observability": observability}


async def _run(output_path: str, *, session_factory: SessionFactory | None = None) -> Path:
    payload = await build_observability_export(session_factory=session_factory)
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        default="openclaw/runtime/observability.json",
        help="Observability output path.",
    )
    args = parser.parse_args()
    output = asyncio.run(_run(args.output))
    print(output.as_posix())


if __name__ == "__main__":
    main()
