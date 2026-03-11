"""Export a machine-readable manifest of repo-complete GitHub issues pending sync."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


REPO_COMPLETE_ISSUES = [
    {
        "issue": 39,
        "title": "Employment & Wages",
        "repo_status": "repo_complete",
        "sync_action": "close_if_acceptance_matches",
        "evidence_commits": ["4b86023"],
    },
    {
        "issue": 40,
        "title": "Player Contract (Escrow)",
        "repo_status": "repo_complete",
        "sync_action": "close_if_acceptance_matches",
        "evidence_commits": ["4b86023"],
    },
    {
        "issue": 41,
        "title": "Notification & Event Feed",
        "repo_status": "repo_complete",
        "sync_action": "close_if_acceptance_matches",
        "evidence_commits": ["4b86023"],
    },
    {
        "issue": 42,
        "title": "Perishable Goods Decay",
        "repo_status": "repo_complete",
        "sync_action": "close_if_acceptance_matches",
        "evidence_commits": ["4b86023"],
    },
    {
        "issue": 43,
        "title": "Event Effects Application",
        "repo_status": "repo_complete",
        "sync_action": "close_if_acceptance_matches",
        "evidence_commits": ["4b86023"],
    },
    {
        "issue": 44,
        "title": "Building Natural Decay",
        "repo_status": "repo_complete",
        "sync_action": "close_if_acceptance_matches",
        "evidence_commits": ["4b86023"],
    },
    {
        "issue": 45,
        "title": "Agent Direct Trade",
        "repo_status": "repo_complete",
        "sync_action": "close_if_acceptance_matches",
        "evidence_commits": ["2c2a843"],
    },
    {
        "issue": 46,
        "title": "Reputation Effects",
        "repo_status": "repo_complete",
        "sync_action": "close_if_acceptance_matches",
        "evidence_commits": ["2c2a843"],
    },
    {
        "issue": 47,
        "title": "NPC Shop Dynamic Pricing",
        "repo_status": "repo_complete",
        "sync_action": "close_if_acceptance_matches",
        "evidence_commits": ["2c2a843"],
    },
    {
        "issue": 48,
        "title": "Agent Carry Capacity",
        "repo_status": "repo_complete",
        "sync_action": "close_if_acceptance_matches",
        "evidence_commits": ["39ac91d"],
    },
    {
        "issue": 49,
        "title": "Treaty Mechanical Effects",
        "repo_status": "repo_complete",
        "sync_action": "close_if_acceptance_matches",
        "evidence_commits": ["8f454da"],
    },
    {
        "issue": 50,
        "title": "Regional Infrastructure",
        "repo_status": "repo_complete",
        "sync_action": "close_if_acceptance_matches",
        "evidence_commits": ["8f454da"],
    },
    {
        "issue": 51,
        "title": "Multi-tier Workforce",
        "repo_status": "repo_complete",
        "sync_action": "close_if_acceptance_matches",
        "evidence_commits": ["09f6990"],
    },
    {
        "issue": 52,
        "title": "Market Order Type",
        "repo_status": "repo_complete",
        "sync_action": "close_if_acceptance_matches",
        "evidence_commits": ["09f6990"],
    },
    {
        "issue": 53,
        "title": "Guild Level & Upgrade",
        "repo_status": "repo_complete",
        "sync_action": "close_if_acceptance_matches",
        "evidence_commits": ["09f6990"],
    },
    {
        "issue": 54,
        "title": "Career Path Effects",
        "repo_status": "repo_complete",
        "sync_action": "close_if_acceptance_matches",
        "evidence_commits": ["09f6990"],
    },
    {
        "issue": 55,
        "title": "Storage Capacity Limits",
        "repo_status": "repo_complete",
        "sync_action": "close_if_acceptance_matches",
        "evidence_commits": ["09f6990"],
    },
    {
        "issue": 64,
        "title": "Server Autopilot — Reflex + Standing Orders",
        "repo_status": "repo_complete",
        "sync_action": "close_if_acceptance_matches",
        "evidence_commits": ["fc20b44"],
    },
    {
        "issue": 65,
        "title": "Rich Information APIs — AI Decision Data",
        "repo_status": "repo_complete",
        "sync_action": "close_if_acceptance_matches",
        "evidence_commits": ["fc20b44"],
    },
    {
        "issue": 66,
        "title": "Goal Tracking System",
        "repo_status": "repo_complete",
        "sync_action": "close_if_acceptance_matches",
        "evidence_commits": ["fc20b44"],
    },
    {
        "issue": 67,
        "title": "Activity Digest / Morning Briefing",
        "repo_status": "repo_complete",
        "sync_action": "close_if_acceptance_matches",
        "evidence_commits": ["fc20b44"],
    },
    {
        "issue": 68,
        "title": "Autonomy Config API",
        "repo_status": "repo_complete",
        "sync_action": "close_if_acceptance_matches",
        "evidence_commits": ["fc20b44"],
    },
    {
        "issue": 69,
        "title": "MCP Tool Suite — AI Agent Core Interface",
        "repo_status": "repo_complete",
        "sync_action": "close_if_acceptance_matches",
        "evidence_commits": ["fc20b44", "3467ac3"],
    },
    {
        "issue": 70,
        "title": "Real-time Activity Dashboard API",
        "repo_status": "repo_complete",
        "sync_action": "close_if_acceptance_matches",
        "evidence_commits": ["fc20b44"],
    },
    {
        "issue": 71,
        "title": "Housekeeping Integration",
        "repo_status": "repo_complete",
        "sync_action": "close_if_acceptance_matches",
        "evidence_commits": ["fc20b44"],
    },
    {
        "issue": 72,
        "title": "MCP Tools Expansion — Repo-Truthful 14 Modules / 60 Tools",
        "repo_status": "local_preview_complete",
        "sync_action": "close_if_local_preview_scope_accepted",
        "evidence_commits": ["3467ac3"],
    },
    {
        "issue": 73,
        "title": "Agentropolis World Skill — MCP-First With Mounted REST Fallback",
        "repo_status": "local_preview_complete",
        "sync_action": "close_if_local_preview_scope_accepted",
        "evidence_commits": ["de8a476"],
    },
    {
        "issue": 74,
        "title": "Agent Brain Decision Framework — System Prompt",
        "repo_status": "local_preview_complete",
        "sync_action": "close_if_local_preview_scope_accepted",
        "evidence_commits": ["de8a476", "ef3f0a5"],
    },
    {
        "issue": 75,
        "title": "OpenClaw Configuration Templates & Registration Flow",
        "repo_status": "local_preview_complete",
        "sync_action": "close_if_local_preview_scope_accepted",
        "evidence_commits": ["98d8c45", "ef3f0a5"],
    },
    {
        "issue": 76,
        "title": "Multi-Agent Deployment Orchestration",
        "repo_status": "local_preview_complete",
        "sync_action": "close_if_local_preview_scope_accepted",
        "evidence_commits": ["98d8c45"],
    },
    {
        "issue": 77,
        "title": "End-to-End Integration Test — Full Agent Lifecycle",
        "repo_status": "local_preview_complete",
        "sync_action": "close_if_local_preview_scope_accepted",
        "evidence_commits": ["98d8c45"],
    },
    {
        "issue": 78,
        "title": "Concurrency Guard Core — StripedLock + GlobalSemaphore",
        "repo_status": "repo_complete",
        "sync_action": "close_if_acceptance_matches",
        "evidence_commits": ["b6f4dc7"],
    },
    {
        "issue": 79,
        "title": "Rate Limit Middleware — Sliding Window",
        "repo_status": "repo_complete",
        "sync_action": "close_if_acceptance_matches",
        "evidence_commits": ["b6f4dc7"],
    },
    {
        "issue": 80,
        "title": "Concurrency Integration — main.py + Exception Handlers",
        "repo_status": "repo_complete",
        "sync_action": "close_if_acceptance_matches",
        "evidence_commits": ["b6f4dc7"],
    },
]


def build_issue_sync_manifest() -> dict:
    return {
        "scope": "created_issues_repo_complete_pending_sync",
        "notes": [
            "This manifest tracks repo-truthful completion for created issues whose GitHub state may still need manual synchronization.",
            "It does not assert that remote issues are already closed.",
            "It covers created issues across the current roadmap, including completed design-gap and autonomy/control-plane ranges.",
            "Proposed backlog #81+ is intentionally excluded because those issues may not exist on GitHub.",
        ],
        "issues": REPO_COMPLETE_ISSUES,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        default="openclaw/runtime/issue-sync-manifest.json",
        help="Issue-sync manifest output path.",
    )
    args = parser.parse_args()
    payload = build_issue_sync_manifest()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
    print(output.as_posix())


if __name__ == "__main__":
    main()
