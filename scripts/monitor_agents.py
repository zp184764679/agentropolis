"""Collect a local-preview fleet snapshot from an Agentropolis agent manifest."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

DEFAULT_MANIFEST = Path("openclaw/runtime/agents.json")


def _headers(api_key: str) -> dict[str, str]:
    return {"X-API-Key": api_key}


def load_manifest(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


async def _safe_get(
    client: httpx.AsyncClient,
    path: str,
    *,
    headers: dict[str, str] | None = None,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    response = await client.get(path, headers=headers, params=params)
    try:
        payload = response.json()
    except Exception:
        payload = {"detail": response.text}
    return {
        "ok": not response.is_error,
        "status_code": response.status_code,
        "payload": payload,
        "request_id": response.headers.get("X-Agentropolis-Request-ID"),
        "error_code": response.headers.get("X-Agentropolis-Error-Code"),
    }


async def collect_fleet_snapshot(
    client: httpx.AsyncClient,
    manifest: dict[str, Any],
) -> dict[str, Any]:
    game_status = await _safe_get(client, "/api/game/status")
    leaderboard = await _safe_get(client, "/api/game/leaderboard")

    agents: list[dict[str, Any]] = []
    for entry in manifest.get("agents", []):
        agent_headers = _headers(entry["agent_api_key"])
        status = await _safe_get(client, "/api/agent/status", headers=agent_headers)
        dashboard = await _safe_get(client, "/api/dashboard", headers=agent_headers)
        digest = await _safe_get(client, "/api/digest", headers=agent_headers)
        autonomy = await _safe_get(client, "/api/autonomy/config", headers=agent_headers)

        company_name = None
        company_net_worth = None
        unread_count = None
        current_region_id = None

        if dashboard["ok"] and dashboard["payload"].get("company"):
            company_name = dashboard["payload"]["company"]["name"]
            company_net_worth = dashboard["payload"]["company"]["net_worth"]
        if digest["ok"]:
            unread_count = digest["payload"]["unread_count"]
        if status["ok"]:
            current_region_id = status["payload"]["current_region_id"]

        agents.append(
            {
                "agent_id": entry["agent_id"],
                "agent_name": entry["agent_name"],
                "company_name": company_name,
                "current_region_id": current_region_id,
                "unread_digest_count": unread_count,
                "company_net_worth": company_net_worth,
                "autonomy_mode": autonomy["payload"]["mode"] if autonomy["ok"] else None,
                "autopilot_enabled": (
                    autonomy["payload"]["autopilot_enabled"] if autonomy["ok"] else None
                ),
                "requests": {
                    "status": status,
                    "dashboard": dashboard,
                    "digest": digest,
                    "autonomy": autonomy,
                },
            }
        )

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "base_url": manifest["base_url"],
        "game_status": game_status,
        "leaderboard": leaderboard,
        "agents": agents,
    }


def write_snapshot(snapshot: dict[str, Any] | list[dict[str, Any]], output: str | Path) -> Path:
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(snapshot, indent=2, ensure_ascii=True), encoding="utf-8")
    return target


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        default=str(DEFAULT_MANIFEST),
        help="Path to the generated agent manifest.",
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("AGENTROPOLIS_BASE_URL"),
        help="Optional override for the base URL stored in the manifest.",
    )
    parser.add_argument(
        "--output",
        default="-",
        help="Output path, or '-' to print JSON to stdout.",
    )
    parser.add_argument("--interval", type=float, default=0.0, help="Polling interval in seconds.")
    parser.add_argument("--iterations", type=int, default=1, help="Number of snapshots to collect.")
    return parser


async def _run(args: argparse.Namespace) -> dict[str, Any] | list[dict[str, Any]]:
    manifest = load_manifest(args.manifest)
    if args.base_url:
        manifest = dict(manifest)
        manifest["base_url"] = args.base_url.rstrip("/")

    snapshots: list[dict[str, Any]] = []
    async with httpx.AsyncClient(base_url=manifest["base_url"].rstrip("/"), timeout=30.0) as client:
        for index in range(args.iterations):
            snapshots.append(await collect_fleet_snapshot(client, manifest))
            if args.interval > 0 and index < args.iterations - 1:
                await asyncio.sleep(args.interval)

    return snapshots[0] if len(snapshots) == 1 else snapshots


def main() -> None:
    args = build_parser().parse_args()
    snapshot = asyncio.run(_run(args))
    if args.output == "-":
        print(json.dumps(snapshot, indent=2, ensure_ascii=True))
        return
    path = write_snapshot(snapshot, args.output)
    print(path.as_posix())


if __name__ == "__main__":
    main()
