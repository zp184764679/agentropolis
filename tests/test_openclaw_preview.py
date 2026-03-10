"""OpenClaw local-preview asset and orchestration tests."""

from __future__ import annotations

import asyncio
from pathlib import Path

from agentropolis.runtime_meta import build_runtime_metadata
from scripts.monitor_agents import collect_fleet_snapshot
from scripts.register_agents import bootstrap_agents, build_default_specs
from tests.contract.parity_helpers import seeded_client


def test_openclaw_runtime_metadata_and_assets_exist() -> None:
    meta = build_runtime_metadata()
    surface = meta["openclaw_surface"]
    prompt_surface = meta["prompt_surface"]

    assert surface["local_preview_only"] is True
    assert surface["prompt_file"] == "prompts/agent-brain.md"
    assert surface["skill_file"] == "skills/agentropolis-world/SKILL.md"
    assert surface["compose_file"] == "docker-compose.multi-agent.yml"
    assert surface["registration_script"] == "scripts/register_agents.py"
    assert surface["monitor_script"] == "scripts/monitor_agents.py"
    assert surface["manifest_output_default"] == "openclaw/runtime/agents.json"
    assert prompt_surface["prompt_asset"]["exists"] is True
    assert prompt_surface["prompt_asset"]["sha256"]
    assert len(prompt_surface["prompt_asset"]["sha256"]) == 64
    assert prompt_surface["prompt_asset"]["bytes"] > 0
    assert len(surface["asset_fingerprints"]) >= 10
    assert all(item["exists"] is True for item in surface["asset_fingerprints"])
    assert all(item["sha256"] and len(item["sha256"]) == 64 for item in surface["asset_fingerprints"])

    expected_paths = [
        Path("prompts/agent-brain.md"),
        Path("openclaw/README.md"),
        Path("openclaw/agent-template.yaml"),
        Path("openclaw/fleet-template.yaml"),
        Path("openclaw/bootstrap.example.env"),
        Path("docker-compose.multi-agent.yml"),
        Path("scripts/register_agents.py"),
        Path("scripts/monitor_agents.py"),
    ]
    for path in expected_paths:
        assert path.exists(), f"Missing expected OpenClaw preview asset: {path}"

    manifest_paths = {item["path"] for item in surface["asset_fingerprints"]}
    assert "skills/agentropolis-world/SKILL.md" in manifest_paths
    assert "skills/agentropolis-world/references/tool-matrix.md" in manifest_paths
    assert "skills/agentropolis-world/references/rest-fallback-map.md" in manifest_paths


def test_openclaw_local_preview_docs_stay_repo_truthful() -> None:
    prompt = Path("prompts/agent-brain.md").read_text(encoding="utf-8")
    bundle = Path("openclaw/README.md").read_text(encoding="utf-8")
    compose = Path("docker-compose.multi-agent.yml").read_text(encoding="utf-8")

    assert "streamable-http" in prompt
    assert "Use MCP first" in prompt
    assert "official OpenClaw product schema" in bundle
    assert "scripts/register_agents.py" in bundle
    assert "scripts/monitor_agents.py" in compose
    assert "openclaw/runtime/agents.json" in compose


def test_openclaw_asset_fingerprints_cover_prompt_skill_and_templates() -> None:
    surface = build_runtime_metadata()["openclaw_surface"]
    fingerprints = {item["path"]: item for item in surface["asset_fingerprints"]}

    prompt_hash = fingerprints["prompts/agent-brain.md"]["sha256"]
    skill_hash = fingerprints["skills/agentropolis-world/SKILL.md"]["sha256"]

    assert prompt_hash != skill_hash
    assert fingerprints["openclaw/agent-template.yaml"]["bytes"] > 0
    assert fingerprints["openclaw/fleet-template.yaml"]["bytes"] > 0
    assert fingerprints["docker-compose.multi-agent.yml"]["bytes"] > 0


def test_register_and_monitor_scripts_work_against_local_asgi_runtime() -> None:
    async def scenario() -> None:
        async with seeded_client() as (client, _session_factory):
            manifest = await bootstrap_agents(
                client,
                build_default_specs(2, prefix="OpenClaw"),
                base_url="http://testserver",
            )
            snapshot = await collect_fleet_snapshot(client, manifest)

            assert manifest["transport"] == "streamable-http"
            assert len(manifest["agents"]) == 2
            assert snapshot["game_status"]["ok"] is True
            assert snapshot["leaderboard"]["ok"] is True
            assert len(snapshot["agents"]) == 2
            assert snapshot["agents"][0]["requests"]["dashboard"]["ok"] is True
            assert snapshot["agents"][0]["autopilot_enabled"] is True

    asyncio.run(scenario())
