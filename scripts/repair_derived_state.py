"""Recompute derived economy state for local-preview recovery drills."""

from __future__ import annotations

import argparse
import asyncio
import json

from agentropolis.database import async_session
from agentropolis.services.recovery_svc import repair_derived_state


async def _run() -> dict:
    async with async_session() as session:
        payload = await repair_derived_state(session)
        await session.commit()
        return payload


def main() -> None:
    argparse.ArgumentParser(description=__doc__).parse_args()
    payload = asyncio.run(_run())
    print(json.dumps(payload, indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()
