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


@cli.command("contract-snapshot")
@click.option(
    "--output",
    default="openclaw/runtime/contract-snapshot.json",
    show_default=True,
    help="Contract snapshot output path.",
)
def contract_snapshot(output: str):
    """Export runtime metadata plus the static MCP registry snapshot."""
    from pathlib import Path

    from scripts.export_contract_snapshot import build_contract_snapshot

    payload = build_contract_snapshot()
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    console.print_json(json.dumps(payload))


@cli.command("rollout-readiness")
@click.option(
    "--output",
    default="openclaw/runtime/rollout-readiness.json",
    show_default=True,
    help="Rollout readiness output path.",
)
def rollout_readiness(output: str):
    """Export current local-preview rollout readiness."""
    from scripts.export_rollout_readiness import build_rollout_readiness_export

    async def _readiness():
        payload = await build_rollout_readiness_export()
        from pathlib import Path

        target = Path(output)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        console.print_json(json.dumps(payload))

    asyncio.run(_readiness())


@cli.command("check-rollout-gate")
@click.option(
    "--readiness",
    default="openclaw/runtime/rollout-readiness.json",
    show_default=True,
    help="Rollout readiness snapshot path.",
)
@click.option(
    "--contract-snapshot",
    default="openclaw/runtime/contract-snapshot.json",
    show_default=True,
    help="Contract snapshot path.",
)
def check_rollout_gate(readiness: str, contract_snapshot: str):
    """Summarize rollout-gate state from exported review artifacts."""
    from pathlib import Path

    from scripts.check_rollout_gate import build_rollout_gate_summary

    readiness_payload = json.loads(Path(readiness).read_text(encoding="utf-8"))
    contract_payload = json.loads(Path(contract_snapshot).read_text(encoding="utf-8"))
    payload = build_rollout_gate_summary(
        readiness_payload["rollout_readiness"],
        contract_payload,
    )
    console.print_json(json.dumps(payload))


@cli.command("alerts-snapshot")
@click.option(
    "--output",
    default="openclaw/runtime/alerts.json",
    show_default=True,
    help="Alerts snapshot output path.",
)
def alerts_snapshot(output: str):
    """Export the current derived alerts snapshot."""
    from scripts.export_alert_snapshot import build_alert_export

    async def _snapshot():
        payload = await build_alert_export()
        from pathlib import Path

        target = Path(output)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        console.print_json(json.dumps(payload))

    asyncio.run(_snapshot())


@cli.command("observability-snapshot")
@click.option(
    "--output",
    default="openclaw/runtime/observability.json",
    show_default=True,
    help="Observability snapshot output path.",
)
def observability_snapshot(output: str):
    """Export the current observability snapshot."""
    from scripts.export_observability_snapshot import build_observability_export

    async def _snapshot():
        payload = await build_observability_export()
        from pathlib import Path

        target = Path(output)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        console.print_json(json.dumps(payload))

    asyncio.run(_snapshot())


@cli.command("execution-snapshot")
@click.option(
    "--output",
    default="openclaw/runtime/execution.json",
    show_default=True,
    help="Execution snapshot output path.",
)
def execution_snapshot(output: str):
    """Export the current execution/job-model snapshot."""
    from scripts.export_execution_snapshot import build_execution_export

    async def _snapshot():
        payload = await build_execution_export()
        from pathlib import Path

        target = Path(output)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        console.print_json(json.dumps(payload))

    asyncio.run(_snapshot())


@cli.command("build-review-bundle")
@click.option(
    "--output-dir",
    default="openclaw/runtime/review-bundle",
    show_default=True,
    help="Review bundle output directory.",
)
def build_review_bundle(output_dir: str):
    """Assemble contract, readiness, observability, and world artifacts into one directory."""
    from scripts.build_review_bundle import build_review_bundle as build_review_bundle_svc

    async def _bundle():
        payload = await build_review_bundle_svc(output_dir)
        console.print_json(json.dumps(payload))

    asyncio.run(_bundle())


@cli.command()
@click.confirmation_option(prompt="This will delete ALL game data. Are you sure?")
def reset():
    """Reset game state. Deletes all companies, orders, trades."""
    raise NotImplementedError("Issue #14: Implement CLI reset command")


if __name__ == "__main__":
    cli()
