"""Economy governance registry for reviewable local-preview tuning."""

from __future__ import annotations

from agentropolis.config import settings


def _entry(value, *, unit: str, owner: str, rationale: str) -> dict:
    return {
        "value": value,
        "unit": unit,
        "owner": owner,
        "rationale": rationale,
    }


def build_tunable_registry() -> dict:
    return {
        "legacy_workers": {
            "WORKER_RAT_PER_TICK": _entry(
                settings.WORKER_RAT_PER_TICK,
                unit="RAT/worker/tick",
                owner="legacy_scaffold",
                rationale="Controls worker food sink.",
            ),
            "WORKER_DW_PER_TICK": _entry(
                settings.WORKER_DW_PER_TICK,
                unit="DW/worker/tick",
                owner="legacy_scaffold",
                rationale="Controls worker water sink.",
            ),
            "SATISFACTION_DECAY_RATE": _entry(
                settings.SATISFACTION_DECAY_RATE,
                unit="pct/tick",
                owner="legacy_scaffold",
                rationale="Sets the downside when workers are undersupplied.",
            ),
            "SATISFACTION_RECOVERY_RATE": _entry(
                settings.SATISFACTION_RECOVERY_RATE,
                unit="pct/tick",
                owner="legacy_scaffold",
                rationale="Sets the recovery speed after supply is restored.",
            ),
        },
        "agent_vitals": {
            "AGENT_HUNGER_DECAY_PER_HOUR": _entry(
                settings.AGENT_HUNGER_DECAY_PER_HOUR,
                unit="points/hour",
                owner="shared_world_kernel",
                rationale="Base hunger decay for all agents.",
            ),
            "AGENT_THIRST_DECAY_PER_HOUR": _entry(
                settings.AGENT_THIRST_DECAY_PER_HOUR,
                unit="points/hour",
                owner="shared_world_kernel",
                rationale="Base thirst decay for all agents.",
            ),
            "AGENT_ENERGY_DECAY_PER_HOUR": _entry(
                settings.AGENT_ENERGY_DECAY_PER_HOUR,
                unit="points/hour",
                owner="shared_world_kernel",
                rationale="Base energy decay for all agents.",
            ),
            "AGENT_EAT_HUNGER_RESTORE": _entry(
                settings.AGENT_EAT_HUNGER_RESTORE,
                unit="points/unit",
                owner="shared_world_kernel",
                rationale="Food restore amount used by agent reflex actions.",
            ),
            "AGENT_DRINK_THIRST_RESTORE": _entry(
                settings.AGENT_DRINK_THIRST_RESTORE,
                unit="points/unit",
                owner="shared_world_kernel",
                rationale="Water restore amount used by agent reflex actions.",
            ),
            "AGENT_REST_ENERGY_RESTORE": _entry(
                settings.AGENT_REST_ENERGY_RESTORE,
                unit="points/action",
                owner="shared_world_kernel",
                rationale="Energy restore amount used by agent reflex actions.",
            ),
        },
        "autonomy": {
            "AUTOPILOT_DEFAULT_SPENDING_LIMIT_PER_HOUR": _entry(
                settings.AUTOPILOT_DEFAULT_SPENDING_LIMIT_PER_HOUR,
                unit="copper/hour",
                owner="autonomy_core",
                rationale="Default hourly spend ceiling for standing orders.",
            ),
            "AUTOPILOT_HUNGER_THRESHOLD": _entry(
                settings.AUTOPILOT_HUNGER_THRESHOLD,
                unit="points",
                owner="autonomy_core",
                rationale="Below this, reflex food consumption is allowed.",
            ),
            "AUTOPILOT_THIRST_THRESHOLD": _entry(
                settings.AUTOPILOT_THIRST_THRESHOLD,
                unit="points",
                owner="autonomy_core",
                rationale="Below this, reflex water consumption is allowed.",
            ),
            "AUTOPILOT_ENERGY_THRESHOLD": _entry(
                settings.AUTOPILOT_ENERGY_THRESHOLD,
                unit="points",
                owner="autonomy_core",
                rationale="Below this, reflex rest is allowed.",
            ),
        },
        "shops_and_warfare": {
            "NPC_SHOP_DEFAULT_ELASTICITY": _entry(
                settings.NPC_SHOP_DEFAULT_ELASTICITY,
                unit="ratio",
                owner="economy_services",
                rationale="Controls NPC price responsiveness.",
            ),
            "NPC_SHOP_MIN_PRICE_MULTIPLIER": _entry(
                settings.NPC_SHOP_MIN_PRICE_MULTIPLIER,
                unit="ratio",
                owner="economy_services",
                rationale="Lower clamp for NPC shop prices.",
            ),
            "NPC_SHOP_MAX_PRICE_MULTIPLIER": _entry(
                settings.NPC_SHOP_MAX_PRICE_MULTIPLIER,
                unit="ratio",
                owner="economy_services",
                rationale="Upper clamp for NPC shop prices.",
            ),
            "WARFARE_CONTRACT_CANCEL_FEE_PCT": _entry(
                settings.WARFARE_CONTRACT_CANCEL_FEE_PCT,
                unit="ratio",
                owner="warfare_services",
                rationale="Controls escrow burn when contracts are cancelled.",
            ),
        },
        "rollout_flags": {
            "PREVIEW_SURFACE_ENABLED": _entry(
                settings.PREVIEW_SURFACE_ENABLED,
                unit="bool",
                owner="control_plane",
                rationale="Top-level preview availability gate.",
            ),
            "PREVIEW_DEGRADED_MODE": _entry(
                settings.PREVIEW_DEGRADED_MODE,
                unit="bool",
                owner="control_plane",
                rationale="Allows read-mostly operation under degraded conditions.",
            ),
            "MCP_SURFACE_ENABLED": _entry(
                settings.MCP_SURFACE_ENABLED,
                unit="bool",
                owner="control_plane",
                rationale="Controls whether the local-preview MCP surface mounts.",
            ),
        },
    }


def build_economy_health_thresholds() -> dict:
    return {
        "inflation_index": {
            "warning_above": 1.25,
            "critical_above": 1.75,
        },
        "worker_satisfaction": {
            "warning_below": settings.LOW_SATISFACTION_THRESHOLD,
            "critical_below": 25.0,
        },
        "agent_vitals": {
            "warning_below": 35.0,
            "critical_below": 15.0,
        },
        "preview_budget": {
            "warning_remaining_below": 5,
            "critical_remaining_below": 1,
        },
    }


def build_governance_snapshot() -> dict:
    return {
        "registry": build_tunable_registry(),
        "thresholds": build_economy_health_thresholds(),
        "review_checklist": [
            "Document which tunables changed and why.",
            "State whether the change is local-preview only or intended for broader rollout.",
            "Run economy and lifecycle regression tests before widening exposure.",
            "Review inflation, worker satisfaction, and autopilot spend thresholds together.",
            "Pair any repair/backfill step with a before/after snapshot artifact.",
        ],
    }
