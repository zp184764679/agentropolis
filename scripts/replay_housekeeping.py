"""Replay housekeeping sweeps for local-preview recovery drills."""

from __future__ import annotations

import argparse
import asyncio
import json

from agentropolis.database import async_session
from agentropolis.services.recovery_svc import replay_housekeeping_range


async def _run(*, start_tick: int, sweeps: int) -> dict:
    async with async_session() as session:
        payload = await replay_housekeeping_range(
            session,
            start_tick=start_tick,
            sweeps=sweeps,
        )
        await session.commit()
        return payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-tick", type=int, required=True, help="First tick to replay.")
    parser.add_argument("--sweeps", type=int, required=True, help="Number of sweeps to replay.")
    args = parser.parse_args()
    payload = asyncio.run(_run(start_tick=args.start_tick, sweeps=args.sweeps))
    print(json.dumps(payload, indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()
