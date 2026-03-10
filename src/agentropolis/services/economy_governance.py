"""Economy governance registry for reviewable local-preview tuning."""

from __future__ import annotations

from agentropolis.config import settings


def _entry(
    value,
    *,
    unit: str,
    owner: str,
    rationale: str,
    source: str = "settings",
) -> dict:
    return {
        "value": value,
        "unit": unit,
        "owner": owner,
        "rationale": rationale,
        "source": source,
    }


def _flag_entry(
    value,
    *,
    owner: str,
    rationale: str,
    stages: list[str] | tuple[str, ...],
    affected_systems: list[str] | tuple[str, ...],
) -> dict:
    return {
        "value": value,
        "owner": owner,
        "rationale": rationale,
        "allowed_stages": list(stages),
        "affected_systems": list(affected_systems),
        "source": "settings",
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
                rationale="Sets the downside when supplies are missing.",
            ),
            "SATISFACTION_RECOVERY_RATE": _entry(
                settings.SATISFACTION_RECOVERY_RATE,
                unit="pct/tick",
                owner="legacy_scaffold",
                rationale="Sets recovery speed after supply is restored.",
            ),
            "WORKER_ATTRITION_RATE": _entry(
                settings.WORKER_ATTRITION_RATE,
                unit="ratio",
                owner="legacy_scaffold",
                rationale="Controls worker loss when satisfaction collapses.",
            ),
        },
        "company_economy": {
            "INITIAL_BALANCE": _entry(
                settings.INITIAL_BALANCE,
                unit="copper",
                owner="economy_services",
                rationale="Starting company balance for new companies.",
            ),
            "INITIAL_WORKERS": _entry(
                settings.INITIAL_WORKERS,
                unit="workers",
                owner="economy_services",
                rationale="Initial worker pool for legacy company scaffolds.",
            ),
            "EMPLOYMENT_DEFAULT_SALARY_PER_SECOND": _entry(
                settings.EMPLOYMENT_DEFAULT_SALARY_PER_SECOND,
                unit="copper/worker/second",
                owner="employment_services",
                rationale="Default worker salary floor for settlements.",
            ),
            "BUILDING_NATURAL_DECAY_PER_HOUR": _entry(
                settings.BUILDING_NATURAL_DECAY_PER_HOUR,
                unit="durability/hour",
                owner="infrastructure_services",
                rationale="Natural maintenance sink applied to buildings.",
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
                rationale="Food restore amount used by reflex actions.",
            ),
            "AGENT_DRINK_THIRST_RESTORE": _entry(
                settings.AGENT_DRINK_THIRST_RESTORE,
                unit="points/unit",
                owner="shared_world_kernel",
                rationale="Water restore amount used by reflex actions.",
            ),
            "AGENT_REST_ENERGY_RESTORE": _entry(
                settings.AGENT_REST_ENERGY_RESTORE,
                unit="points/action",
                owner="shared_world_kernel",
                rationale="Energy restore amount used by rest actions.",
            ),
            "AGENT_RESPAWN_PENALTY": _entry(
                settings.AGENT_RESPAWN_PENALTY,
                unit="ratio",
                owner="shared_world_kernel",
                rationale="Penalty multiplier applied on respawn.",
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
            "AUTOPILOT_MAX_RULES_PER_SWEEP": _entry(
                settings.AUTOPILOT_MAX_RULES_PER_SWEEP,
                unit="rules/sweep",
                owner="autonomy_core",
                rationale="Upper bound on standing-order throughput per sweep.",
            ),
        },
        "regional_projects": {
            "PROJECT_ROAD_IMPROVEMENT_COST": _entry(
                settings.PROJECT_ROAD_IMPROVEMENT_COST,
                unit="copper",
                owner="regional_projects",
                rationale="Road-improvement capital sink.",
            ),
            "PROJECT_MARKET_EXPANSION_COST": _entry(
                settings.PROJECT_MARKET_EXPANSION_COST,
                unit="copper",
                owner="regional_projects",
                rationale="Market-expansion capital sink.",
            ),
            "PROJECT_FORTIFICATION_COST": _entry(
                settings.PROJECT_FORTIFICATION_COST,
                unit="copper",
                owner="regional_projects",
                rationale="Fortification capital sink.",
            ),
            "PROJECT_TRADE_HUB_COST": _entry(
                settings.PROJECT_TRADE_HUB_COST,
                unit="copper",
                owner="regional_projects",
                rationale="Trade-hub capital sink.",
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
            "critical_above": 2.0,
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
        "source_sink": {
            "open_orders_warning_above": 100,
            "overdue_transports_warning_above": 1,
            "overdue_transports_critical_above": 5,
            "tax_collected_warning_below": 0,
        },
        "market_volatility": {
            "warning_abs_delta_pct": 15.0,
            "critical_abs_delta_pct": 35.0,
        },
    }


def build_staged_rollout_flags() -> dict:
    return {
        "ECONOMY_BALANCE_PROFILE": _flag_entry(
            settings.ECONOMY_BALANCE_PROFILE,
            owner="economy_governance",
            rationale="Named balance profile to support explicit review and rollback discussion.",
            stages=["local_preview_default", "stress_test", "closed_beta_candidate"],
            affected_systems=["economy_governance", "review_bundle", "regression_tests"],
        ),
        "ECONOMY_DYNAMIC_PRICING_STAGE": _flag_entry(
            settings.ECONOMY_DYNAMIC_PRICING_STAGE,
            owner="economy_services",
            rationale="Stages rollout of NPC dynamic pricing and similar elasticity-driven price changes.",
            stages=["disabled", "local_preview", "closed_beta", "wider_rollout"],
            affected_systems=["npc_shop_svc", "observability", "economy_regression"],
        ),
        "ECONOMY_TRANSPORT_TAX_STAGE": _flag_entry(
            settings.ECONOMY_TRANSPORT_TAX_STAGE,
            owner="economy_services",
            rationale="Stages transport-tax tuning and validation before wider rollout.",
            stages=["disabled", "local_preview", "closed_beta", "wider_rollout"],
            affected_systems=["tax_svc", "transport_svc", "observability"],
        ),
        "ECONOMY_AUTOPILOT_MARKET_STAGE": _flag_entry(
            settings.ECONOMY_AUTOPILOT_MARKET_STAGE,
            owner="autonomy_core",
            rationale="Stages increasingly aggressive autopilot market participation.",
            stages=["disabled", "reflex_only", "assisted_only", "wider_rollout"],
            affected_systems=["autopilot", "market_engine", "digest_svc"],
        ),
        "ECONOMY_NXC_HALVING_STAGE": _flag_entry(
            settings.ECONOMY_NXC_HALVING_STAGE,
            owner="nxc_mining",
            rationale="Stages NXC emission and halving behavior for preview and balance review.",
            stages=["disabled", "local_preview", "closed_beta", "wider_rollout"],
            affected_systems=["nxc_mining_svc", "game_engine", "observability"],
        ),
    }


def build_balance_review_checklist() -> list[str]:
    return [
        "Document which tunables changed and why.",
        "State whether the change is local-preview only or intended for broader rollout.",
        "Reference the active economy balance profile and staged-rollout flags.",
        "Run economy and lifecycle regression tests before widening exposure.",
        "Review inflation, worker satisfaction, and autopilot spend thresholds together.",
        "Check observability snapshots for stuck-work, starvation, and execution-lag signals.",
        "Pair any repair/backfill step with a before/after snapshot artifact.",
    ]


def build_economic_regression_scenarios() -> list[dict]:
    return [
        {
            "scenario_id": "production_trade_cycle",
            "title": "Production -> inventory -> market transfer remains solvent",
            "tests": [
                "tests/test_economy_convergence.py::test_agent_company_production_market_path",
                "tests/test_economy_regression.py::test_governance_regression_catalog_matches_executable_scenarios",
            ],
            "threshold_refs": ["inflation_index", "source_sink", "market_volatility"],
            "owner": "economy_services",
        },
        {
            "scenario_id": "worker_starvation_recovery",
            "title": "Worker starvation penalties and recovery remain bounded",
            "tests": [
                "tests/test_consumption.py::test_tick_consumption_decays_satisfaction_and_causes_attrition_when_unsupplied",
                "tests/test_consumption.py::test_tick_consumption_recovers_satisfaction_when_supplied",
            ],
            "threshold_refs": ["worker_satisfaction", "source_sink"],
            "owner": "legacy_scaffold",
        },
        {
            "scenario_id": "autonomy_budget_market_guardrails",
            "title": "Autonomy market participation honors spend and mutation guardrails",
            "tests": [
                "tests/test_autonomy_core.py::test_housekeeping_drives_autonomy_goal_digest_dashboard_and_intel",
                "tests/test_preview_guard.py::test_company_market_write_enforces_spend_caps_and_operation_refill",
            ],
            "threshold_refs": ["preview_budget", "agent_vitals"],
            "owner": "autonomy_core",
        },
        {
            "scenario_id": "housekeeping_currency_supply",
            "title": "Housekeeping keeps currency supply and inflation observable after settlement",
            "tests": [
                "tests/test_economy_convergence.py::test_housekeeping_cycle_updates_game_state_and_log",
            ],
            "threshold_refs": ["inflation_index", "source_sink"],
            "owner": "economy_services",
        },
    ]


def build_parameter_ownership_index() -> dict:
    ownership: dict[str, list[str]] = {}
    registry = build_tunable_registry()
    for entries in registry.values():
        for name, spec in entries.items():
            ownership.setdefault(spec["owner"], []).append(name)
    for name, spec in build_staged_rollout_flags().items():
        ownership.setdefault(spec["owner"], []).append(name)
    return {
        owner: sorted(parameters)
        for owner, parameters in sorted(ownership.items())
    }


def build_governance_snapshot() -> dict:
    return {
        "registry": build_tunable_registry(),
        "thresholds": build_economy_health_thresholds(),
        "staged_rollout_flags": build_staged_rollout_flags(),
        "review_checklist": build_balance_review_checklist(),
        "regression_scenarios": build_economic_regression_scenarios(),
        "ownership_index": build_parameter_ownership_index(),
        "balance_profile": settings.ECONOMY_BALANCE_PROFILE,
    }
