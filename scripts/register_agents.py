"""Bootstrap one or more Agentropolis agents for local-preview external runners."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

DEFAULT_BASE_URL = "http://localhost:8000"
DEFAULT_OUTPUT = Path("openclaw/runtime/agents.json")
DEFAULT_PROMPT_FILE = "prompts/agent-brain.md"
DEFAULT_SKILL_FILE = "skills/agentropolis-world/SKILL.md"
DEFAULT_AGENT_TEMPLATE = "openclaw/agent-template.yaml"
DEFAULT_FLEET_TEMPLATE = "openclaw/fleet-template.yaml"


def build_default_specs(count: int, prefix: str = "Preview Agent") -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = []
    for index in range(1, count + 1):
        agent_name = f"{prefix} {index:02d}"
        specs.append(
            {
                "agent_name": agent_name,
                "company_name": f"{agent_name} Works",
                "autonomy_config": {
                    "autopilot_enabled": True,
                    "mode": "assisted",
                    "spending_limit_per_hour": 250,
                },
                "standing_orders": {"buy_rules": [], "sell_rules": []},
            }
        )
    return specs


def load_specs(spec_file: str | None, count: int, prefix: str) -> list[dict[str, Any]]:
    if not spec_file:
        return build_default_specs(count, prefix=prefix)

    payload = json.loads(Path(spec_file).read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        payload = payload.get("agents", [])
    if not isinstance(payload, list):
        raise ValueError("Spec file must contain a list or an object with an 'agents' list.")
    return [dict(item) for item in payload]


def _headers(api_key: str) -> dict[str, str]:
    return {"X-API-Key": api_key}


async def _require_json(response: httpx.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except Exception:
        payload = {"detail": response.text}

    if response.is_error:
        request_id = response.headers.get("X-Agentropolis-Request-ID")
        error_code = response.headers.get("X-Agentropolis-Error-Code")
        raise RuntimeError(
            f"{response.request.method} {response.request.url.path} -> {response.status_code} "
            f"(error_code={error_code}, request_id={request_id}): {payload}"
        )
    return payload


async def bootstrap_agents(
    client: httpx.AsyncClient,
    specs: list[dict[str, Any]],
    *,
    base_url: str,
) -> dict[str, Any]:
    manifest_agents: list[dict[str, Any]] = []

    for index, raw_spec in enumerate(specs, start=1):
        spec = dict(raw_spec)
        agent_name = spec["agent_name"]
        company_name = spec.get("company_name")

        register_payload = {"name": agent_name}
        if spec.get("home_region_id") is not None:
            register_payload["home_region_id"] = spec["home_region_id"]

        registered = await _require_json(
            await client.post("/api/agent/register", json=register_payload)
        )
        agent_api_key = registered["api_key"]

        company_payload = None
        if company_name:
            company_payload = await _require_json(
                await client.post(
                    "/api/agent/company",
                    headers=_headers(agent_api_key),
                    json={"company_name": company_name},
                )
            )

        if spec.get("autonomy_config"):
            await _require_json(
                await client.put(
                    "/api/autonomy/config",
                    headers=_headers(agent_api_key),
                    json=spec["autonomy_config"],
                )
            )

        if spec.get("standing_orders") is not None:
            await _require_json(
                await client.put(
                    "/api/autonomy/standing-orders",
                    headers=_headers(agent_api_key),
                    json={"standing_orders": spec["standing_orders"]},
                )
            )

        dashboard = await _require_json(
            await client.get("/api/dashboard", headers=_headers(agent_api_key))
        )

        env_prefix = f"OPENCLAW_AGENT_{index:02d}"
        manifest_agents.append(
            {
                "index": index,
                "agent_name": registered["name"],
                "agent_id": registered["agent_id"],
                "home_region_id": registered["home_region_id"],
                "current_region_id": registered["current_region_id"],
                "agent_api_key": agent_api_key,
                "agent_api_key_env": f"{env_prefix}_AGENT_API_KEY",
                "company_name": company_payload["company_name"] if company_payload else None,
                "company_id": company_payload["company_id"] if company_payload else None,
                "company_api_key": company_payload["api_key"] if company_payload else None,
                "company_api_key_env": f"{env_prefix}_COMPANY_API_KEY",
                "dashboard_company_name": (
                    dashboard["company"]["name"] if dashboard.get("company") else None
                ),
                "autonomy_mode": dashboard["autonomy"]["mode"],
                "autopilot_enabled": dashboard["autonomy"]["autopilot_enabled"],
            }
        )

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "base_url": base_url.rstrip("/"),
        "mcp_url": f"{base_url.rstrip('/')}/mcp",
        "transport": "streamable-http",
        "prompt_file": DEFAULT_PROMPT_FILE,
        "skill_file": DEFAULT_SKILL_FILE,
        "agent_template": DEFAULT_AGENT_TEMPLATE,
        "fleet_template": DEFAULT_FLEET_TEMPLATE,
        "agents": manifest_agents,
    }


def write_manifest(manifest: dict[str, Any], output_path: str | Path) -> Path:
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(manifest, indent=2, ensure_ascii=True), encoding="utf-8")
    return target


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url",
        default=os.environ.get("AGENTROPOLIS_BASE_URL", DEFAULT_BASE_URL),
        help="Agentropolis base URL.",
    )
    parser.add_argument(
        "--spec-file",
        help="Optional JSON file with agent specs. Supports a list or {'agents': [...]}",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=1,
        help="Default agent count when no spec file is provided.",
    )
    parser.add_argument(
        "--prefix",
        default="Preview Agent",
        help="Name prefix when generating default agent specs.",
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT),
        help="Manifest output path.",
    )
    return parser


async def _run(args: argparse.Namespace) -> Path:
    specs = load_specs(args.spec_file, args.count, args.prefix)
    async with httpx.AsyncClient(base_url=args.base_url.rstrip("/"), timeout=30.0) as client:
        manifest = await bootstrap_agents(client, specs, base_url=args.base_url)
    return write_manifest(manifest, args.output)


def main() -> None:
    args = build_parser().parse_args()
    output = asyncio.run(_run(args))
    print(output.as_posix())


if __name__ == "__main__":
    main()
