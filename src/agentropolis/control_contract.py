"""Machine-readable local-preview contract and authorization catalogs."""

from __future__ import annotations

from copy import deepcopy

from agentropolis.services.concurrency import (
    CONCURRENCY_ERROR_CODES,
    ERROR_CODE_HEADER,
)

CONTROL_CONTRACT_VERSION = "2026-03-preview.1"
CONTRACT_VERSION_HEADER = "X-Agentropolis-Contract-Version"
IDEMPOTENCY_KEY_HEADER = "X-Idempotency-Key"
REQUEST_ID_HEADER = "X-Agentropolis-Request-ID"

AUTH_ERROR_CODES = {
    "auth_api_key_missing": "X-API-Key header is required for this operation.",
    "auth_company_api_key_invalid": "Presented company API key is invalid or inactive.",
    "auth_agent_api_key_invalid": "Presented agent API key is invalid or inactive.",
    "auth_agent_model_unavailable": "Agent auth model exists in the target design but is not active in this runtime.",
}

GENERAL_ERROR_CODES = {
    "request_validation_failed": "Request payload, path params, or query params failed validation.",
    "not_implemented": "Legacy scaffold handler is mounted but not implemented yet.",
}

AUTHORIZATION_ACTOR_KINDS = [
    "public",
    "agent",
    "company",
    "admin",
]

REST_ROUTE_SCOPE_GROUPS = [
    {
        "prefix": "/health",
        "actor_kind": "public",
        "scope_family": None,
        "read_policy": "public",
        "write_policy": "none",
        "idempotency_policy": "safe_read",
        "execution_semantics": "sync",
        "dangerous_operations": [],
    },
    {
        "prefix": "/meta/runtime",
        "actor_kind": "public",
        "scope_family": None,
        "read_policy": "public",
        "write_policy": "none",
        "idempotency_policy": "safe_read",
        "execution_semantics": "sync",
        "dangerous_operations": [],
    },
    {
        "prefix": "/meta/contract",
        "actor_kind": "public",
        "scope_family": None,
        "read_policy": "public",
        "write_policy": "none",
        "idempotency_policy": "safe_read",
        "execution_semantics": "sync",
        "dangerous_operations": [],
    },
    {
        "prefix": "/meta/control-plane",
        "actor_kind": "admin",
        "scope_family": "control_plane",
        "read_policy": "admin_token",
        "write_policy": "admin_token_plus_entity_lock",
        "idempotency_policy": "mixed_admin_actions",
        "execution_semantics": "sync",
        "dangerous_operations": [
            "runtime_policy_updates",
            "per_agent_policy_replace",
            "budget_refill",
            "policy_delete",
            "rate_limit_reset",
        ],
    },
    {
        "prefix": "/meta/observability",
        "actor_kind": "public",
        "scope_family": None,
        "read_policy": "public",
        "write_policy": "none",
        "idempotency_policy": "safe_read",
        "execution_semantics": "sync",
        "dangerous_operations": [],
    },
    {
        "prefix": "/meta/alerts",
        "actor_kind": "public",
        "scope_family": None,
        "read_policy": "public",
        "write_policy": "none",
        "idempotency_policy": "safe_read",
        "execution_semantics": "sync",
        "dangerous_operations": [],
    },
    {
        "prefix": "/meta/rollout-readiness",
        "actor_kind": "public",
        "scope_family": None,
        "read_policy": "public",
        "write_policy": "none",
        "idempotency_policy": "safe_read",
        "execution_semantics": "sync",
        "dangerous_operations": [],
    },
    {
        "prefix": "/api/agent",
        "actor_kind": "mixed_public_agent",
        "scope_family": "agent_self",
        "read_policy": "family_scoped_for_authenticated_reads",
        "write_policy": "preview_policy_plus_entity_lock",
        "idempotency_policy": "mixed_register_create_mutate",
        "execution_semantics": "sync_committed",
        "dangerous_operations": [
            "agent_registration",
            "company_creation",
            "vitals_mutations",
        ],
    },
    {
        "prefix": "/api/world",
        "actor_kind": "mixed_public_agent",
        "scope_family": "world",
        "read_policy": "public_map_region_plus_family_scoped_travel_reads",
        "write_policy": "preview_policy_plus_entity_lock",
        "idempotency_policy": "mixed_read_and_travel_start",
        "execution_semantics": "sync_committed",
        "dangerous_operations": ["travel_start"],
    },
    {
        "prefix": "/api/skills",
        "actor_kind": "mixed_public_agent",
        "scope_family": "strategy",
        "read_policy": "public_definitions_plus_family_scoped_agent_reads",
        "write_policy": "none",
        "idempotency_policy": "safe_read",
        "execution_semantics": "sync",
        "dangerous_operations": [],
    },
    {
        "prefix": "/api/transport",
        "actor_kind": "agent",
        "scope_family": "transport",
        "read_policy": "family_scoped",
        "write_policy": "preview_policy_plus_entity_lock",
        "idempotency_policy": "mixed_transport_create",
        "execution_semantics": "sync_committed",
        "dangerous_operations": ["transport_create"],
    },
    {
        "prefix": "/api/guild",
        "actor_kind": "agent",
        "scope_family": "social",
        "read_policy": "family_scoped",
        "write_policy": "preview_policy_plus_multi_entity_lock",
        "idempotency_policy": "mixed_social_mutations",
        "execution_semantics": "sync_committed",
        "dangerous_operations": [
            "guild_create",
            "guild_join_leave",
            "guild_promote",
            "guild_disband",
        ],
    },
    {
        "prefix": "/api/diplomacy",
        "actor_kind": "agent",
        "scope_family": "social",
        "read_policy": "family_scoped",
        "write_policy": "preview_policy_plus_multi_entity_lock",
        "idempotency_policy": "mixed_social_mutations",
        "execution_semantics": "sync_committed",
        "dangerous_operations": [
            "treaty_propose_accept",
            "relationship_set",
        ],
    },
    {
        "prefix": "/api/strategy",
        "actor_kind": "agent",
        "scope_family": "strategy",
        "read_policy": "family_scoped",
        "write_policy": "preview_policy_plus_entity_lock",
        "idempotency_policy": "mixed_profile_replace",
        "execution_semantics": "sync_committed",
        "dangerous_operations": ["strategy_profile_update"],
    },
    {
        "prefix": "/api/agent/decisions",
        "actor_kind": "agent",
        "scope_family": "strategy",
        "read_policy": "family_scoped",
        "write_policy": "none",
        "idempotency_policy": "safe_read",
        "execution_semantics": "sync",
        "dangerous_operations": [],
    },
    {
        "prefix": "/api/warfare",
        "actor_kind": "agent",
        "scope_family": "warfare",
        "read_policy": "family_scoped",
        "write_policy": "preview_policy_plus_multi_entity_lock",
        "idempotency_policy": "mixed_contract_mutations",
        "execution_semantics": "sync_committed",
        "dangerous_operations": [
            "contract_create_activate_execute_cancel",
            "garrison_assign_remove",
            "building_repair",
        ],
    },
    {
        "prefix": "/api/autonomy",
        "actor_kind": "agent",
        "scope_family": "strategy",
        "read_policy": "family_scoped",
        "write_policy": "preview_policy_plus_entity_lock",
        "idempotency_policy": "mixed_replace_and_goal_mutations",
        "execution_semantics": "sync_committed",
        "dangerous_operations": [
            "autonomy_config_update",
            "standing_order_replace",
            "goal_create_update",
        ],
    },
    {
        "prefix": "/api/digest",
        "actor_kind": "agent",
        "scope_family": "strategy",
        "read_policy": "family_scoped",
        "write_policy": "preview_policy_plus_entity_lock",
        "idempotency_policy": "ack_is_effectively_idempotent",
        "execution_semantics": "sync_committed",
        "dangerous_operations": ["digest_acknowledge"],
    },
    {
        "prefix": "/api/dashboard",
        "actor_kind": "agent",
        "scope_family": "strategy",
        "read_policy": "family_scoped",
        "write_policy": "none",
        "idempotency_policy": "safe_read",
        "execution_semantics": "sync",
        "dangerous_operations": [],
    },
    {
        "prefix": "/api/intel",
        "actor_kind": "agent",
        "scope_family": "strategy",
        "read_policy": "family_scoped",
        "write_policy": "none",
        "idempotency_policy": "safe_read",
        "execution_semantics": "sync",
        "dangerous_operations": [],
    },
    {
        "prefix": "/api/company",
        "actor_kind": "mixed_agent_company",
        "scope_family": "agent_self_or_company",
        "read_policy": "agent_creation_plus_company_status_reads",
        "write_policy": "agent_creation_plus_entity_lock",
        "idempotency_policy": "mixed_create_and_status",
        "execution_semantics": "sync_committed",
        "dangerous_operations": ["legacy_company_register"],
    },
    {
        "prefix": "/api/inventory",
        "actor_kind": "mixed_company_public",
        "scope_family": "company_inventory",
        "read_policy": "company_or_public_resource_info",
        "write_policy": "none",
        "idempotency_policy": "safe_read",
        "execution_semantics": "sync",
        "dangerous_operations": [],
    },
    {
        "prefix": "/api/market",
        "actor_kind": "mixed_company_public",
        "scope_family": "company_market",
        "read_policy": "public_market_reads_plus_company_order_reads",
        "write_policy": "company_auth_plus_entity_lock",
        "idempotency_policy": "mixed_order_mutations",
        "execution_semantics": "sync_committed",
        "dangerous_operations": [
            "place_buy_order",
            "place_sell_order",
            "cancel_order",
        ],
    },
    {
        "prefix": "/api/production",
        "actor_kind": "mixed_company_public",
        "scope_family": "company_production",
        "read_policy": "public_recipe_reads_plus_company_building_reads",
        "write_policy": "company_auth_plus_entity_lock",
        "idempotency_policy": "mixed_building_mutations",
        "execution_semantics": "sync_committed",
        "dangerous_operations": [
            "build_building",
            "start_production",
            "stop_production",
        ],
    },
    {
        "prefix": "/api/game",
        "actor_kind": "mixed_public_company",
        "scope_family": None,
        "read_policy": "public_status_plus_optional_company_leaderboard_context",
        "write_policy": "none",
        "idempotency_policy": "safe_read",
        "execution_semantics": "sync",
        "dangerous_operations": [],
    },
]

_MCP_TOOL_GROUP_SPECS = [
    {
        "module": "agent",
        "actor_kind": "mixed_public_agent",
        "scope_family": "agent_self",
        "rest_fallback_prefix": "/api/agent",
        "tools": [
            "register_agent",
            "get_agent_status",
            "eat",
            "drink",
            "rest",
            "get_agent_profile",
        ],
        "mutation_tools": {
            "register_agent": "non_idempotent_create",
            "eat": "non_idempotent_mutation",
            "drink": "non_idempotent_mutation",
            "rest": "non_idempotent_mutation",
        },
        "dangerous_tools": {"eat", "drink", "rest"},
    },
    {
        "module": "world",
        "actor_kind": "agent",
        "scope_family": "world",
        "rest_fallback_prefix": "/api/world",
        "tools": [
            "get_world_map",
            "get_region_info",
            "get_route",
            "start_travel",
            "get_travel_status",
        ],
        "mutation_tools": {"start_travel": "non_idempotent_mutation"},
        "dangerous_tools": {"start_travel"},
    },
    {
        "module": "inventory",
        "actor_kind": "mixed_company_public",
        "scope_family": "company_inventory",
        "rest_fallback_prefix": "/api/inventory",
        "tools": [
            "get_inventory",
            "get_inventory_item",
            "get_resource_info",
        ],
        "mutation_tools": {},
        "dangerous_tools": set(),
    },
    {
        "module": "market",
        "actor_kind": "company",
        "scope_family": "company_market",
        "rest_fallback_prefix": "/api/market",
        "tools": [
            "get_market_prices",
            "get_order_book",
            "get_price_history",
            "get_trade_history",
            "place_buy_order",
            "place_sell_order",
            "cancel_order",
            "get_my_orders",
        ],
        "mutation_tools": {
            "place_buy_order": "non_idempotent_mutation",
            "place_sell_order": "non_idempotent_mutation",
            "cancel_order": "non_idempotent_mutation",
        },
        "dangerous_tools": {"place_buy_order", "place_sell_order", "cancel_order"},
    },
    {
        "module": "npc",
        "actor_kind": "agent",
        "scope_family": "strategy",
        "rest_fallback_prefix": None,
        "tools": [
            "list_region_shops",
            "get_shop_effective_prices",
        ],
        "mutation_tools": {},
        "dangerous_tools": set(),
    },
    {
        "module": "production",
        "actor_kind": "company",
        "scope_family": "company_production",
        "rest_fallback_prefix": "/api/production",
        "tools": [
            "get_recipes",
            "get_building_types",
            "build_building",
            "start_production",
            "stop_production",
        ],
        "mutation_tools": {
            "build_building": "non_idempotent_mutation",
            "start_production": "non_idempotent_mutation",
            "stop_production": "non_idempotent_mutation",
        },
        "dangerous_tools": {"build_building", "start_production", "stop_production"},
    },
    {
        "module": "company",
        "actor_kind": "agent",
        "scope_family": "agent_self",
        "rest_fallback_prefix": "/api/agent/company",
        "tools": [
            "create_company",
            "get_company",
            "get_company_workers",
            "get_company_buildings",
        ],
        "mutation_tools": {"create_company": "non_idempotent_create"},
        "dangerous_tools": {"create_company"},
    },
    {
        "module": "transport",
        "actor_kind": "agent",
        "scope_family": "transport",
        "rest_fallback_prefix": "/api/transport",
        "tools": [
            "create_transport",
            "get_transport_status",
            "get_my_transports",
        ],
        "mutation_tools": {"create_transport": "non_idempotent_mutation"},
        "dangerous_tools": {"create_transport"},
    },
    {
        "module": "skills",
        "actor_kind": "agent",
        "scope_family": "strategy",
        "rest_fallback_prefix": "/api/skills",
        "tools": [
            "get_skill_definitions",
            "get_my_skills",
        ],
        "mutation_tools": {},
        "dangerous_tools": set(),
    },
    {
        "module": "social",
        "actor_kind": "agent",
        "scope_family": "social",
        "rest_fallback_prefix": "/api/guild_or_diplomacy",
        "tools": [
            "create_guild",
            "get_guild",
            "list_guilds",
            "join_guild",
            "leave_guild",
            "treaty_tool",
            "relationship_tool",
        ],
        "mutation_tools": {
            "create_guild": "non_idempotent_mutation",
            "join_guild": "non_idempotent_mutation",
            "leave_guild": "non_idempotent_mutation",
            "treaty_tool": "mixed_action_tool",
            "relationship_tool": "mixed_action_tool",
        },
        "dangerous_tools": {
            "create_guild",
            "join_guild",
            "leave_guild",
            "treaty_tool",
            "relationship_tool",
        },
    },
    {
        "module": "warfare",
        "actor_kind": "agent",
        "scope_family": "warfare",
        "rest_fallback_prefix": "/api/warfare",
        "tools": [
            "create_contract",
            "list_contracts",
            "contract_action_tool",
            "get_region_threats",
        ],
        "mutation_tools": {
            "create_contract": "non_idempotent_mutation",
            "contract_action_tool": "mixed_action_tool",
        },
        "dangerous_tools": {"create_contract", "contract_action_tool"},
    },
    {
        "module": "strategy",
        "actor_kind": "agent",
        "scope_family": "strategy",
        "rest_fallback_prefix": "/api/autonomy_or_strategy_or_digest_ordashboard",
        "tools": [
            "strategy_profile_tool",
            "autonomy_tool",
            "digest_tool",
            "briefing_tool",
        ],
        "mutation_tools": {
            "strategy_profile_tool": "mixed_action_tool",
            "autonomy_tool": "mixed_action_tool",
            "digest_tool": "mixed_action_tool",
        },
        "dangerous_tools": {
            "strategy_profile_tool",
            "autonomy_tool",
            "digest_tool",
        },
    },
    {
        "module": "notifications",
        "actor_kind": "agent",
        "scope_family": "strategy",
        "rest_fallback_prefix": None,
        "tools": [
            "get_notifications",
            "mark_notification_read",
        ],
        "mutation_tools": {"mark_notification_read": "idempotent_mutation"},
        "dangerous_tools": {"mark_notification_read"},
    },
    {
        "module": "intel",
        "actor_kind": "mixed_public_agent",
        "scope_family": "strategy",
        "rest_fallback_prefix": "/api/intel_or_game",
        "tools": [
            "get_market_intel",
            "get_route_intel",
            "get_opportunities",
            "get_game_status",
            "get_leaderboard",
        ],
        "mutation_tools": {},
        "dangerous_tools": set(),
    },
]


def build_error_taxonomy() -> dict[str, str]:
    from agentropolis.api.preview_guard import ERROR_CODE_CATALOG as preview_error_codes

    merged = dict(GENERAL_ERROR_CODES)
    merged.update(AUTH_ERROR_CODES)
    merged.update(preview_error_codes)
    merged.update(CONCURRENCY_ERROR_CODES)
    return merged


def build_mcp_tool_scope_catalog() -> list[dict]:
    entries: list[dict] = []
    for group in _MCP_TOOL_GROUP_SPECS:
        mutation_tools = group["mutation_tools"]
        dangerous_tools = group["dangerous_tools"]
        for tool_name in group["tools"]:
            entries.append(
                {
                    "tool_name": tool_name,
                    "module": group["module"],
                    "actor_kind": group["actor_kind"],
                    "scope_family": group["scope_family"],
                    "rest_fallback_prefix": group["rest_fallback_prefix"],
                    "execution_semantics": "sync_committed"
                    if tool_name in mutation_tools
                    else "sync",
                    "idempotency_policy": mutation_tools.get(tool_name, "safe_read"),
                    "dangerous_operation": tool_name in dangerous_tools,
                }
            )
    return sorted(entries, key=lambda entry: entry["tool_name"])


def build_control_contract_catalog() -> dict:
    return {
        "version": CONTROL_CONTRACT_VERSION,
        "minimum_contract_frozen": True,
        "local_preview_only": True,
        "public_rollout_ready": False,
        "transport": {
            "mcp": "streamable-http",
            "legacy_transports_supported": [],
        },
        "versioning": {
            "strategy": "contract_version_header_and_metadata",
            "header": CONTRACT_VERSION_HEADER,
            "current": CONTROL_CONTRACT_VERSION,
        },
        "headers": {
            "request_id": REQUEST_ID_HEADER,
            "error_code": ERROR_CODE_HEADER,
            "contract_version": CONTRACT_VERSION_HEADER,
            "idempotency_key": IDEMPOTENCY_KEY_HEADER,
        },
        "idempotency": {
            "policy": "declared_per_route_family_and_tool",
            "idempotency_key_support": "declared_not_enforced",
            "header": IDEMPOTENCY_KEY_HEADER,
        },
        "pagination": {
            "policy": "limit_offset_preview",
            "limit_query_params": ["limit", "offset", "ticks"],
            "cursor_query_params": [],
        },
        "execution_semantics": {
            "default": "sync",
            "state_mutations": "sync_committed",
            "async_acceptance": [],
            "housekeeping_follow_up": "best_effort_background",
        },
        "authorization": {
            "actor_kinds": list(AUTHORIZATION_ACTOR_KINDS),
            "rest_route_scopes": deepcopy(REST_ROUTE_SCOPE_GROUPS),
            "mcp_tool_scopes": build_mcp_tool_scope_catalog(),
            "dangerous_operation_gates": [
                "preview_policy_family_authz",
                "authenticated_request_rate_limit",
                "authenticated_request_slot_gate",
                "entity_locks_for_writes",
                "admin_token_for_control_plane",
            ],
        },
        "error_taxonomy": build_error_taxonomy(),
    }
