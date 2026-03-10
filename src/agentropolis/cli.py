"""CLI management commands.

Usage:
    agentropolis seed     - Seed scaffold economy + target world baseline
    agentropolis reset    - Reset game state (dangerous!)
    agentropolis stats    - Show game statistics
    agentropolis run      - Start the game server

Dependencies: services/seed.py, services/seed_world.py, database.py
"""

import asyncio
import json

import click
from rich.console import Console

console = Console()


@click.group()
def cli():
    """Agentropolis - AI-native simulated world and control plane."""
    pass


@cli.command()
def seed():
    """Seed scaffold economy data and the minimum target world graph."""
    from agentropolis.database import async_session
    from agentropolis.services.seed import seed_game_data
    from agentropolis.services.seed_world import seed_world

    async def _seed():
        async with async_session() as session:
            game_result = await seed_game_data(session)
            world_result = await seed_world(session)
            console.print(f"[green]Seeded game:[/green] {game_result}")
            console.print(f"[green]Seeded world:[/green] {world_result}")

    asyncio.run(_seed())


@cli.command()
def run():
    """Start the game server."""
    import uvicorn
    from agentropolis.config import settings

    uvicorn.run(
        "agentropolis.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        log_level=settings.LOG_LEVEL.lower(),
    )


@cli.command()
def stats():
    """Show game statistics."""
    from agentropolis.services.economy_governance import build_governance_snapshot

    snapshot = build_governance_snapshot()
    console.print_json(json.dumps(snapshot))


@cli.command("world-snapshot")
@click.option(
    "--output",
    default="openclaw/runtime/world-snapshot.json",
    show_default=True,
    help="Snapshot output path.",
)
def world_snapshot(output: str):
    """Export a world snapshot for local-preview recovery drills."""
    from agentropolis.database import async_session
    from agentropolis.services.recovery_svc import build_world_snapshot

    async def _snapshot():
        async with async_session() as session:
            payload = await build_world_snapshot(session)
            console.print_json(json.dumps(payload))
            if output:
                from pathlib import Path

                target = Path(output)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    asyncio.run(_snapshot())


@cli.command("repair-derived-state")
def repair_derived_state():
    """Recompute derived economy state such as net worth and inflation."""
    from agentropolis.database import async_session
    from agentropolis.services.recovery_svc import repair_derived_state as repair_derived_state_svc

    async def _repair():
        async with async_session() as session:
            payload = await repair_derived_state_svc(session)
            await session.commit()
            console.print_json(json.dumps(payload))

    asyncio.run(_repair())


@cli.command()
@click.confirmation_option(prompt="This will delete ALL game data. Are you sure?")
def reset():
    """Reset game state. Deletes all companies, orders, trades."""
    raise NotImplementedError("Issue #14: Implement CLI reset command")


if __name__ == "__main__":
    cli()
