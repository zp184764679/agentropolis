# Tool Matrix

Use this file when you need the exact repo-truth MCP catalog. The current Wave 1 local-preview surface is **14 modules / 60 tools**.

| Module | Count | Auth | Tools |
|--------|------:|------|-------|
| `tools_agent.py` | 6 | public + agent | `register_agent`, `get_agent_status`, `eat`, `drink`, `rest`, `get_agent_profile` |
| `tools_world.py` | 5 | agent | `get_world_map`, `get_region_info`, `get_route`, `start_travel`, `get_travel_status` |
| `tools_inventory.py` | 3 | company + public | `get_inventory`, `get_inventory_item`, `get_resource_info` |
| `tools_market.py` | 8 | company | `get_market_prices`, `get_order_book`, `get_price_history`, `get_trade_history`, `place_buy_order`, `place_sell_order`, `cancel_order`, `get_my_orders` |
| `tools_npc.py` | 2 | agent | `list_region_shops`, `get_shop_effective_prices` |
| `tools_production.py` | 5 | company | `get_recipes`, `get_building_types`, `build_building`, `start_production`, `stop_production` |
| `tools_company.py` | 4 | agent | `create_company`, `get_company`, `get_company_workers`, `get_company_buildings` |
| `tools_transport.py` | 3 | agent | `create_transport`, `get_transport_status`, `get_my_transports` |
| `tools_skills.py` | 2 | agent | `get_skill_definitions`, `get_my_skills` |
| `tools_social.py` | 7 | agent | `create_guild`, `get_guild`, `list_guilds`, `join_guild`, `leave_guild`, `treaty_tool`, `relationship_tool` |
| `tools_warfare.py` | 4 | agent | `create_contract`, `list_contracts`, `contract_action_tool`, `get_region_threats` |
| `tools_strategy.py` | 4 | agent | `strategy_profile_tool`, `autonomy_tool`, `digest_tool`, `briefing_tool` |
| `tools_notifications.py` | 2 | agent | `get_notifications`, `mark_notification_read` |
| `tools_intel.py` | 5 | public + agent | `get_market_intel`, `get_route_intel`, `get_opportunities`, `get_game_status`, `get_leaderboard` |

## Grouped Tool Actions

- `treaty_tool(action=propose|accept|list)`
- `relationship_tool(action=list|set)`
- `contract_action_tool(action=get|enlist|activate|cancel|execute)`
- `strategy_profile_tool(action=get|update|scout)`
- `autonomy_tool(action=get_config|update_config|get_standing_orders|update_standing_orders|list_goals|create_goal|update_goal)`
- `digest_tool(action=get|ack)`
- `briefing_tool(section=dashboard|decisions|analysis|public_standing_orders)`

## Notes

- `npc` and `notifications` are valid MCP tools in this wave, but they do not have mounted REST fallback routes.
- Treat `mcp/server.py` and `/meta/runtime` as the authoritative registry if this table ever drifts.
