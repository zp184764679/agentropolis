"""CLI management commands.

Usage:
    agentropolis seed     - Seed scaffold economy + target world baseline
    agentropolis reset    - Reset game state (dangerous!)
    agentropolis stats    - Show game statistics
    agentropolis run      - Start the game server

Dependencies: services/seed.py, services/seed_world.py, database.py
"""

import asyncio

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
    raise NotImplementedError("Issue #14: Implement CLI stats command")


@cli.command()
@click.confirmation_option(prompt="This will delete ALL game data. Are you sure?")
def reset():
    """Reset game state. Deletes all companies, orders, trades."""
    raise NotImplementedError("Issue #14: Implement CLI reset command")


if __name__ == "__main__":
    cli()
