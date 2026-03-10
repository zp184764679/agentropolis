"""Broader REST/MCP contract parity coverage for mounted gameplay surfaces."""

from __future__ import annotations

import asyncio
import re

from agentropolis.mcp.tools_agent import (
    drink,
    eat,
    get_agent_profile,
    get_agent_status,
    register_agent,
    rest,
)
from agentropolis.mcp.tools_company import (
    create_company,
    get_company,
    get_company_buildings,
    get_company_workers,
)
from agentropolis.mcp.tools_intel import (
    get_game_status,
    get_leaderboard,
    get_market_intel,
    get_opportunities,
    get_route_intel,
)
from agentropolis.mcp.tools_inventory import (
    get_inventory,
    get_inventory_item,
    get_resource_info,
)
from agentropolis.mcp.tools_market import (
    get_market_prices,
    get_my_orders,
    get_order_book,
    get_price_history,
    get_trade_history,
    place_sell_order,
)
from agentropolis.mcp.tools_production import (
    build_building,
    get_building_types,
    get_recipes,
    start_production,
    stop_production,
)
from agentropolis.mcp.tools_skills import get_my_skills, get_skill_definitions
from agentropolis.mcp.tools_social import (
    create_guild,
    get_guild,
    join_guild,
    leave_guild,
    list_guilds,
    relationship_tool,
    treaty_tool,
)
from agentropolis.mcp.tools_strategy import autonomy_tool, briefing_tool, digest_tool, strategy_profile_tool
from agentropolis.mcp.tools_transport import get_my_transports, get_transport_status
from agentropolis.mcp.tools_warfare import contract_action_tool, create_contract, get_region_threats, list_contracts
from agentropolis.mcp.tools_world import get_region_info, get_route, get_world_map
from tests.contract.parity_helpers import api_key_headers, seeded_client


def _sorted(items: list[dict], key: str) -> list[dict]:
    return sorted(items, key=lambda item: item[key])


def _assert_error_equivalent(rest_response, mcp_payload: dict) -> None:
    assert mcp_payload["ok"] is False
    assert mcp_payload["status_code"] == rest_response.status_code
    assert mcp_payload["detail"] == rest_response.json()["detail"]
    assert mcp_payload["error_code"] == rest_response.json().get("error_code")


def _assert_agent_status_equivalent(rest_payload: dict, mcp_payload: dict) -> None:
    for field in (
        "agent_id",
        "name",
        "current_region_id",
        "home_region_id",
        "personal_balance",
        "is_alive",
        "career_path",
    ):
        assert mcp_payload[field] == rest_payload[field]
    for field in ("health", "hunger", "thirst", "energy", "happiness", "reputation"):
        assert abs(float(mcp_payload[field]) - float(rest_payload[field])) <= 0.01


def _normalized_dashboard(payload: dict) -> dict:
    normalized = dict(payload)
    normalized["generated_at"] = "<generated>"
    autonomy = dict(normalized["autonomy"])
    autonomy["hour_window_started_at"] = "<window>"
    normalized["autonomy"] = autonomy
    return normalized


def _normalized_inventory_items(items: list[dict]) -> list[dict]:
    normalized: list[dict] = []
    for item in items:
        normalized.append(
            {
                key: value
                for key, value in item.items()
                if key in {"ticker", "name", "quantity", "reserved", "available"}
            }
        )
    return _sorted(normalized, "ticker")


def _normalized_inventory_item(item: dict) -> dict:
    return {
        key: value
        for key, value in item.items()
        if key in {"ticker", "name", "quantity", "reserved", "available"}
    }


def _normalized_standing_orders(payload: dict) -> dict:
    normalized = {"buy_rules": [], "sell_rules": []}
    for key in ("buy_rules", "sell_rules"):
        rules = []
        for rule in payload.get(key, []):
            item = dict(rule)
            item.setdefault("source", None)
            rules.append(item)
        normalized[key] = rules
    return normalized


def _normalized_digest(payload: dict) -> dict:
    normalized = dict(payload)
    normalized["generated_at"] = "<generated>"
    return normalized


def _normalized_message(message: str) -> str:
    return re.sub(r"\d+(?:\.\d+)?", "<n>", message)


def _normalized_guild(payload: dict) -> dict:
    normalized = dict(payload)
    normalized["members"] = sorted(
        [
            {
                key: value
                for key, value in member.items()
                if key in {"agent_id", "rank", "share_percentage", "joined_at"}
            }
            for member in payload.get("members", [])
        ],
        key=lambda member: member["agent_id"],
    )
    return normalized


def test_rest_and_mcp_cover_agent_world_company_transport_and_intel_parity() -> None:
    async def scenario() -> None:
        async with seeded_client() as (client, _session_factory):
            created_agent = await register_agent("Parity Core Agent")
            assert created_agent["ok"] is True

            agent_id = created_agent["agent"]["agent_id"]
            agent_api_key = created_agent["agent"]["api_key"]

            created_company = await create_company(agent_api_key, "Parity Core Works")
            assert created_company["ok"] is True

            rest_status = await client.get("/api/agent/status", headers=api_key_headers(agent_api_key))
            rest_profile = await client.get(
                f"/api/agent/profile/{agent_id}",
                headers=api_key_headers(agent_api_key),
            )
            rest_company = await client.get(
                "/api/agent/company",
                headers=api_key_headers(agent_api_key),
            )
            rest_workers = await client.get(
                "/api/agent/company/workers",
                headers=api_key_headers(agent_api_key),
            )
            rest_buildings = await client.get(
                "/api/agent/company/buildings",
                headers=api_key_headers(agent_api_key),
            )
            rest_world_map = await client.get("/api/world/map")
            rest_region = await client.get("/api/world/region/1")
            rest_route = await client.get(
                "/api/intel/routes",
                headers=api_key_headers(agent_api_key),
                params={"to_region_id": 2},
            )
            rest_market_intel = await client.get(
                "/api/intel/market/H2O",
                headers=api_key_headers(agent_api_key),
            )
            rest_opportunities = await client.get(
                "/api/intel/opportunities",
                headers=api_key_headers(agent_api_key),
            )
            rest_skill_defs = await client.get("/api/skills/definitions")
            rest_my_skills = await client.get(
                "/api/skills/mine",
                headers=api_key_headers(agent_api_key),
            )
            rest_resource = await client.get("/api/inventory/info/H2O")

            assert all(
                response.status_code == 200
                for response in (
                    rest_status,
                    rest_profile,
                    rest_company,
                    rest_workers,
                    rest_buildings,
                    rest_world_map,
                    rest_region,
                    rest_route,
                    rest_market_intel,
                    rest_opportunities,
                    rest_skill_defs,
                    rest_my_skills,
                    rest_resource,
                )
            )

            mcp_status = await get_agent_status(agent_api_key)
            mcp_profile = await get_agent_profile(agent_api_key, agent_id)
            mcp_company = await get_company(agent_api_key)
            mcp_workers = await get_company_workers(agent_api_key)
            mcp_buildings = await get_company_buildings(agent_api_key)
            mcp_world_map = await get_world_map(agent_api_key)
            mcp_region = await get_region_info(agent_api_key, region_id=1)
            mcp_route = await get_route(agent_api_key, to_region_id=2)
            mcp_market_intel = await get_market_intel(agent_api_key, "H2O")
            mcp_route_intel = await get_route_intel(agent_api_key, to_region_id=2)
            mcp_opportunities = await get_opportunities(agent_api_key)
            mcp_skill_defs = await get_skill_definitions(agent_api_key)
            mcp_my_skills = await get_my_skills(agent_api_key)
            mcp_resource = await get_resource_info("H2O")

            _assert_agent_status_equivalent(rest_status.json(), mcp_status["agent"])
            assert mcp_profile["profile"] == rest_profile.json()
            assert mcp_company["company"] == rest_company.json()
            assert mcp_workers["workers"] == rest_workers.json()
            assert mcp_buildings["buildings"] == rest_buildings.json()
            assert mcp_world_map["regions"] == rest_world_map.json()["regions"]
            assert mcp_region["region"] == rest_region.json()
            assert mcp_route["route"] == rest_route.json()
            assert mcp_route_intel["intel"] == rest_route.json()
            assert mcp_market_intel["intel"] == rest_market_intel.json()
            assert mcp_opportunities["intel"] == rest_opportunities.json()
            assert mcp_skill_defs["ok"] is True
            assert _sorted(mcp_skill_defs["skills"], "skill_name") == _sorted(rest_skill_defs.json(), "skill_name")
            assert _sorted(mcp_my_skills["skills"], "skill_name") == _sorted(rest_my_skills.json(), "skill_name")
            assert mcp_resource["resource"] == rest_resource.json()

            rest_transport = await client.post(
                "/api/transport/create",
                headers=api_key_headers(agent_api_key),
                json={
                    "from_region_id": 1,
                    "to_region_id": 2,
                    "items": {"RAT": 1},
                    "transport_type": "backpack",
                },
            )
            assert rest_transport.status_code == 200
            transport_id = rest_transport.json()["transport_id"]

            rest_transport_status = await client.get(
                f"/api/transport/status/{transport_id}",
                headers=api_key_headers(agent_api_key),
            )
            rest_transports = await client.get(
                "/api/transport/mine",
                headers=api_key_headers(agent_api_key),
            )
            assert rest_transport_status.status_code == 200
            assert rest_transports.status_code == 200

            mcp_transport_status = await get_transport_status(agent_api_key, transport_id)
            mcp_transports = await get_my_transports(agent_api_key)

            assert mcp_transport_status["transport"] == rest_transport_status.json()
            assert mcp_transports["transports"] == rest_transports.json()

    asyncio.run(scenario())


def test_rest_and_mcp_cover_market_production_inventory_and_game_parity() -> None:
    async def scenario() -> None:
        async with seeded_client() as (client, _session_factory):
            seller = await register_agent("Parity Seller")
            buyer = await register_agent("Parity Buyer")
            assert seller["ok"] is True
            assert buyer["ok"] is True

            seller_key = seller["agent"]["api_key"]
            buyer_key = buyer["agent"]["api_key"]

            seller_company = await create_company(seller_key, "Parity Seller Works")
            buyer_company = await create_company(buyer_key, "Parity Buyer Works")
            assert seller_company["ok"] is True
            assert buyer_company["ok"] is True

            seller_company_key = seller_company["company"]["api_key"]
            buyer_company_key = buyer_company["company"]["api_key"]

            rest_building_types = await client.get("/api/production/building-types")
            rest_recipes = await client.get("/api/production/recipes")
            rest_prices = await client.get("/api/market/prices")
            rest_order_book = await client.get("/api/market/orderbook/H2O")
            rest_analysis = await client.get("/api/market/analysis/H2O")
            rest_game_status = await client.get("/api/game/status")
            rest_leaderboard = await client.get("/api/game/leaderboard")

            assert all(
                response.status_code == 200
                for response in (
                    rest_building_types,
                    rest_recipes,
                    rest_prices,
                    rest_order_book,
                    rest_analysis,
                    rest_game_status,
                    rest_leaderboard,
                )
            )

            mcp_building_types = await get_building_types(seller_company_key)
            mcp_recipes = await get_recipes(seller_company_key)
            mcp_prices = await get_market_prices(seller_company_key)
            mcp_order_book = await get_order_book(seller_company_key, "H2O")
            mcp_game_status = await get_game_status()
            mcp_leaderboard = await get_leaderboard()

            assert _sorted(mcp_building_types["building_types"], "name") == _sorted(rest_building_types.json(), "name")
            assert _sorted(mcp_recipes["recipes"], "recipe_id") == _sorted(rest_recipes.json(), "recipe_id")
            assert mcp_prices["prices"] == rest_prices.json()
            assert mcp_order_book["order_book"] == rest_order_book.json()
            assert mcp_game_status["status"] == rest_game_status.json()
            assert mcp_leaderboard["leaderboard"] == rest_leaderboard.json()

            rest_buildings = await client.get(
                "/api/agent/company/buildings",
                headers=api_key_headers(seller_key),
            )
            assert rest_buildings.status_code == 200
            mcp_company_buildings = await get_company_buildings(seller_key)
            assert mcp_company_buildings["buildings"] == rest_buildings.json()

            active_company_buildings = rest_buildings.json()
            extractor = next(
                building
                for building in active_company_buildings
                if building["building_type"] == "extractor"
            )
            building_id = extractor["building_id"]
            matching_recipe = next(
                recipe
                for recipe in rest_recipes.json()
                if recipe["building_type"] == extractor["building_type"]
            )

            mcp_start = await start_production(
                seller_company_key,
                building_id=building_id,
                recipe_id=matching_recipe["recipe_id"],
            )
            assert mcp_start["ok"] is True

            rest_started_buildings = await client.get(
                "/api/production/buildings",
                headers=api_key_headers(seller_company_key),
            )
            assert rest_started_buildings.status_code == 200
            active_building = next(
                building
                for building in rest_started_buildings.json()
                if building["building_id"] == building_id
            )
            assert active_building["active_recipe"] == mcp_start["production"]["recipe"]

            rest_stop = await client.post(
                "/api/production/stop",
                headers=api_key_headers(seller_company_key),
                params={"building_id": building_id},
            )
            assert rest_stop.status_code == 200

            mcp_stopped = await stop_production(seller_company_key, building_id=building_id)
            assert mcp_stopped["ok"] is True

            mcp_sell = await place_sell_order(
                seller_company_key,
                resource="H2O",
                quantity=5,
                price=6,
            )
            assert mcp_sell["ok"] is True

            rest_buy = await client.post(
                "/api/market/buy",
                headers=api_key_headers(buyer_company_key),
                json={"resource": "H2O", "quantity": 5, "price": 6},
            )
            assert rest_buy.status_code == 200

            rest_trades = await client.get("/api/market/trades", params={"ticker": "H2O"})
            rest_history = await client.get("/api/market/history/H2O")
            rest_orders = await client.get(
                "/api/market/orders",
                headers=api_key_headers(seller_company_key),
                params={"status": "ALL"},
            )
            rest_inventory = await client.get(
                "/api/inventory",
                headers=api_key_headers(seller_company_key),
            )
            rest_inventory_item = await client.get(
                "/api/inventory/H2O",
                headers=api_key_headers(seller_company_key),
            )

            assert all(
                response.status_code == 200
                for response in (
                    rest_trades,
                    rest_history,
                    rest_orders,
                    rest_inventory,
                    rest_inventory_item,
                )
            )

            mcp_trade_history = await get_trade_history(seller_company_key, resource="H2O")
            mcp_price_history = await get_price_history(seller_company_key, resource="H2O")
            mcp_orders = await get_my_orders(seller_company_key, status="ALL")
            mcp_inventory = await get_inventory(seller_company_key)
            mcp_inventory_item = await get_inventory_item(seller_company_key, resource="H2O")

            assert mcp_trade_history["trades"] == rest_trades.json()
            assert mcp_price_history["history"] == rest_history.json()
            assert mcp_orders["orders"] == rest_orders.json()
            assert _normalized_inventory_items(mcp_inventory["items"]) == _normalized_inventory_items(
                rest_inventory.json()["items"]
            )
            assert _normalized_inventory_item(mcp_inventory_item["item"]) == _normalized_inventory_item(
                rest_inventory_item.json()
            )
            assert rest_analysis.json()["ticker"] == "H2O"

    asyncio.run(scenario())


def test_rest_and_mcp_cover_strategy_social_and_warfare_parity() -> None:
    async def scenario() -> None:
        async with seeded_client() as (client, _session_factory):
            leader = await register_agent("Parity Leader")
            ally = await register_agent("Parity Ally")
            assert leader["ok"] is True
            assert ally["ok"] is True

            leader_key = leader["agent"]["api_key"]
            ally_key = ally["agent"]["api_key"]
            ally_id = ally["agent"]["agent_id"]

            leader_company = await create_company(leader_key, "Parity Command")
            assert leader_company["ok"] is True

            rest_profile_update = await client.put(
                "/api/strategy/profile",
                headers=api_key_headers(leader_key),
                json={
                    "combat_doctrine": "DEFENSIVE",
                    "risk_tolerance": 0.4,
                    "primary_focus": "LEADERSHIP",
                    "secondary_focus": "COMMERCE",
                    "default_stance": "OPEN",
                },
            )
            assert rest_profile_update.status_code == 200

            rest_profile = await client.get(
                "/api/strategy/profile",
                headers=api_key_headers(leader_key),
            )
            rest_dashboard = await client.get(
                "/api/dashboard",
                headers=api_key_headers(leader_key),
            )
            rest_decisions = await client.get(
                "/api/agent/decisions",
                headers=api_key_headers(leader_key),
            )
            rest_decision_analysis = await client.get(
                "/api/agent/decisions/analysis",
                headers=api_key_headers(leader_key),
            )
            assert all(
                response.status_code == 200
                for response in (
                    rest_profile,
                    rest_dashboard,
                    rest_decisions,
                    rest_decision_analysis,
                )
            )

            mcp_profile = await strategy_profile_tool(leader_key, action="get")
            mcp_decisions = await briefing_tool(leader_key, section="decisions")
            mcp_analysis = await briefing_tool(leader_key, section="analysis")
            mcp_dashboard = await briefing_tool(leader_key, section="dashboard")

            assert mcp_profile["profile"] == rest_profile.json()
            assert mcp_decisions["briefing"] == rest_decisions.json()
            assert mcp_analysis["briefing"] == rest_decision_analysis.json()
            assert _normalized_dashboard(mcp_dashboard["briefing"]) == _normalized_dashboard(rest_dashboard.json())

            updated_config = await autonomy_tool(
                leader_key,
                action="update_config",
                autopilot_enabled=True,
                mode="assisted",
                spending_limit_per_hour=120,
            )
            updated_orders = await autonomy_tool(
                leader_key,
                action="update_standing_orders",
                standing_orders={
                    "buy_rules": [{"resource": "H2O", "below_price": 7, "max_qty": 5}],
                    "sell_rules": [],
                },
            )
            created_goal = await autonomy_tool(
                leader_key,
                action="create_goal",
                goal_type="ACCUMULATE_RESOURCE",
                target={"resource": "H2O", "quantity": 100},
                priority=10,
                notes="Parity goal",
            )
            assert updated_config["ok"] is True
            assert updated_orders["ok"] is True
            assert created_goal["ok"] is True

            rest_config = await client.get(
                "/api/autonomy/config",
                headers=api_key_headers(leader_key),
            )
            rest_orders = await client.get(
                "/api/autonomy/standing-orders",
                headers=api_key_headers(leader_key),
            )
            rest_goals = await client.get(
                "/api/autonomy/goals",
                headers=api_key_headers(leader_key),
            )
            rest_digest = await client.get(
                "/api/digest",
                headers=api_key_headers(leader_key),
            )
            rest_public_standing_orders = await client.get(
                "/api/strategy/standing-orders",
                headers=api_key_headers(leader_key),
                params={"region_id": 1},
            )
            assert all(
                response.status_code == 200
                for response in (
                    rest_config,
                    rest_orders,
                    rest_goals,
                    rest_digest,
                    rest_public_standing_orders,
                )
            )

            mcp_config = await autonomy_tool(leader_key, action="get_config")
            mcp_orders = await autonomy_tool(leader_key, action="get_standing_orders")
            mcp_goals = await autonomy_tool(leader_key, action="list_goals")
            mcp_digest = await digest_tool(leader_key, action="get")
            mcp_public_standing_orders = await briefing_tool(
                leader_key,
                section="public_standing_orders",
                region_id=1,
            )

            assert mcp_config["config"] == rest_config.json()
            assert _normalized_standing_orders(mcp_orders["standing_orders"]) == _normalized_standing_orders(
                rest_orders.json()["standing_orders"]
            )
            assert mcp_goals["goals"] == rest_goals.json()["goals"]
            assert _normalized_digest(mcp_digest["digest"]) == _normalized_digest(rest_digest.json())
            assert mcp_public_standing_orders["briefing"] == rest_public_standing_orders.json()

            rest_guild = await client.post(
                "/api/guild/create",
                headers=api_key_headers(leader_key),
                json={"name": "Parity Guild", "home_region_id": 1},
            )
            assert rest_guild.status_code == 200
            guild_id = rest_guild.json()["guild_id"]

            mcp_guild = await get_guild(leader_key, guild_id)
            mcp_guilds = await list_guilds(leader_key)
            assert _normalized_guild(mcp_guild["guild"]) == _normalized_guild(rest_guild.json())
            assert any(guild["guild_id"] == guild_id for guild in mcp_guilds["guilds"])

            joined = await join_guild(ally_key, guild_id)
            assert joined["ok"] is True

            rest_guild_after_join = await client.get(f"/api/guild/{guild_id}")
            assert rest_guild_after_join.status_code == 200
            assert mcp_guild["guild"]["name"] == rest_guild_after_join.json()["name"]
            assert rest_guild_after_join.json()["member_count"] == 2

            rest_relationship = await client.post(
                "/api/diplomacy/relationship",
                headers=api_key_headers(leader_key),
                json={
                    "target_agent_id": ally_id,
                    "relation_type": "allied",
                    "trust_delta": 5,
                },
            )
            assert rest_relationship.status_code == 200

            mcp_relationships = await relationship_tool(leader_key, action="list")
            assert rest_relationship.json() in mcp_relationships["relationships"]

            proposed_treaty = await treaty_tool(
                leader_key,
                action="propose",
                treaty_type="alliance",
                target_agent_id=ally_id,
                terms={"scope": "trade"},
            )
            assert proposed_treaty["ok"] is True

            treaty_id = proposed_treaty["treaty"]["treaty_id"]
            rest_accept = await client.post(
                f"/api/diplomacy/treaty/{treaty_id}/accept",
                headers=api_key_headers(ally_key),
            )
            assert rest_accept.status_code == 200

            rest_treaties = await client.get(
                "/api/diplomacy/treaties",
                headers=api_key_headers(leader_key),
                params={"active_only": False},
            )
            mcp_treaties = await treaty_tool(leader_key, action="list", active_only=False)
            assert rest_treaties.status_code == 200
            assert mcp_treaties["treaties"] == rest_treaties.json()

            rest_target_transport = await client.post(
                "/api/transport/create",
                headers=api_key_headers(leader_key),
                json={
                    "from_region_id": 1,
                    "to_region_id": 2,
                    "items": {"RAT": 1},
                    "transport_type": "backpack",
                },
            )
            assert rest_target_transport.status_code == 200
            target_transport_id = rest_target_transport.json()["transport_id"]

            rest_contract = await client.post(
                "/api/warfare/contracts",
                headers=api_key_headers(leader_key),
                json={
                    "mission_type": "raid_transport",
                    "target_region_id": 2,
                    "reward_per_agent": 100,
                    "max_agents": 1,
                    "target_transport_id": target_transport_id,
                },
            )
            assert rest_contract.status_code == 200
            contract_id = rest_contract.json()["contract_id"]

            mcp_contract = await contract_action_tool(
                leader_key,
                action="get",
                contract_id=contract_id,
            )
            rest_contract_list = await client.get("/api/warfare/contracts")
            mcp_contract_list = await list_contracts(leader_key)
            rest_threats = await client.get("/api/warfare/region/2/threats")
            mcp_threats = await get_region_threats(leader_key, region_id=2)

            assert mcp_contract["contract"] == rest_contract.json()
            assert mcp_contract_list["contracts"] == rest_contract_list.json()["contracts"]
            assert mcp_threats["threats"] == rest_threats.json()

    asyncio.run(scenario())


def test_rest_and_mcp_cover_mutation_message_parity_for_agent_and_company_flows() -> None:
    async def scenario() -> None:
        async with seeded_client() as (client, _session_factory):
            rest_agent = await register_agent("Parity Rest Mutator")
            mcp_agent = await register_agent("Parity MCP Mutator")
            assert rest_agent["ok"] is True
            assert mcp_agent["ok"] is True

            rest_agent_key = rest_agent["agent"]["api_key"]
            mcp_agent_key = mcp_agent["agent"]["api_key"]

            rest_eat = await client.post(
                "/api/agent/eat",
                headers=api_key_headers(rest_agent_key),
                params={"amount": 1},
            )
            mcp_eat = await eat(mcp_agent_key, amount=1)
            assert rest_eat.status_code == 200
            assert mcp_eat["ok"] is True
            assert _normalized_message(mcp_eat["message"]) == _normalized_message(rest_eat.json()["message"])

            rest_drink = await client.post(
                "/api/agent/drink",
                headers=api_key_headers(rest_agent_key),
                params={"amount": 1},
            )
            mcp_drink = await drink(mcp_agent_key, amount=1)
            assert rest_drink.status_code == 200
            assert mcp_drink["ok"] is True
            assert _normalized_message(mcp_drink["message"]) == _normalized_message(rest_drink.json()["message"])

            rest_rest = await client.post(
                "/api/agent/rest",
                headers=api_key_headers(rest_agent_key),
            )
            mcp_rest = await rest(mcp_agent_key)
            assert rest_rest.status_code == 200
            assert mcp_rest["ok"] is True
            assert _normalized_message(mcp_rest["message"]) == _normalized_message(rest_rest.json()["message"])

            rest_owner = await register_agent("Parity Rest Builder")
            mcp_owner = await register_agent("Parity MCP Builder")
            assert rest_owner["ok"] is True
            assert mcp_owner["ok"] is True

            rest_company = await create_company(rest_owner["agent"]["api_key"], "Parity Rest Builder Works")
            mcp_company = await create_company(mcp_owner["agent"]["api_key"], "Parity MCP Builder Works")
            assert rest_company["ok"] is True
            assert mcp_company["ok"] is True

            rest_company_key = rest_company["company"]["api_key"]
            mcp_company_key = mcp_company["company"]["api_key"]

            rest_build = await client.post(
                "/api/production/build",
                headers=api_key_headers(rest_company_key),
                json={"building_type": "extractor"},
            )
            mcp_build = await build_building(mcp_company_key, "extractor")
            assert rest_build.status_code == 200
            assert mcp_build["ok"] is True
            assert _normalized_message(mcp_build["message"]) == _normalized_message(rest_build.json()["message"])

            rest_buildings = await client.get(
                "/api/production/buildings",
                headers=api_key_headers(rest_company_key),
            )
            mcp_buildings = await client.get(
                "/api/production/buildings",
                headers=api_key_headers(mcp_company_key),
            )
            rest_recipes = await client.get("/api/production/recipes")
            assert rest_buildings.status_code == 200
            assert mcp_buildings.status_code == 200
            assert rest_recipes.status_code == 200

            recipe = next(
                item for item in rest_recipes.json() if item["building_type"] == "extractor"
            )
            rest_building_id = next(
                building["building_id"]
                for building in rest_buildings.json()
                if building["building_type"] == "extractor" and building["active_recipe"] is None
            )
            mcp_building_id = next(
                building["building_id"]
                for building in mcp_buildings.json()
                if building["building_type"] == "extractor" and building["active_recipe"] is None
            )

            rest_start = await client.post(
                "/api/production/start",
                headers=api_key_headers(rest_company_key),
                json={"building_id": rest_building_id, "recipe_id": recipe["recipe_id"]},
            )
            mcp_start = await start_production(
                mcp_company_key,
                building_id=mcp_building_id,
                recipe_id=recipe["recipe_id"],
            )
            assert rest_start.status_code == 200
            assert mcp_start["ok"] is True
            assert _normalized_message(mcp_start["message"]) == _normalized_message(rest_start.json()["message"])

            rest_stop = await client.post(
                "/api/production/stop",
                headers=api_key_headers(rest_company_key),
                params={"building_id": rest_building_id},
            )
            mcp_stop = await stop_production(mcp_company_key, building_id=mcp_building_id)
            assert rest_stop.status_code == 200
            assert mcp_stop["ok"] is True
            assert _normalized_message(mcp_stop["message"]) == _normalized_message(rest_stop.json()["message"])

    asyncio.run(scenario())


def test_rest_and_mcp_cover_mutation_message_parity_for_social_and_warfare() -> None:
    async def scenario() -> None:
        async with seeded_client() as (client, _session_factory):
            rest_leader = await register_agent("Parity Rest Leader")
            rest_member = await register_agent("Parity Rest Member")
            mcp_leader = await register_agent("Parity MCP Leader")
            mcp_member = await register_agent("Parity MCP Member")
            assert all(
                created["ok"] is True
                for created in (rest_leader, rest_member, mcp_leader, mcp_member)
            )

            rest_leader_key = rest_leader["agent"]["api_key"]
            rest_member_key = rest_member["agent"]["api_key"]
            mcp_leader_key = mcp_leader["agent"]["api_key"]
            mcp_member_key = mcp_member["agent"]["api_key"]

            rest_guild = await client.post(
                "/api/guild/create",
                headers=api_key_headers(rest_leader_key),
                json={"name": "Parity Rest Guild", "home_region_id": 1},
            )
            mcp_guild = await create_guild(mcp_leader_key, "Parity MCP Guild", 1)
            assert rest_guild.status_code == 200
            assert mcp_guild["ok"] is True

            rest_guild_id = rest_guild.json()["guild_id"]
            mcp_guild_id = mcp_guild["guild"]["guild_id"]

            rest_join = await client.post(
                f"/api/guild/{rest_guild_id}/join",
                headers=api_key_headers(rest_member_key),
            )
            mcp_join = await join_guild(mcp_member_key, mcp_guild_id)
            assert rest_join.status_code == 200
            assert mcp_join["ok"] is True
            assert _normalized_message(mcp_join["message"]) == _normalized_message(rest_join.json()["message"])

            rest_leave = await client.post(
                f"/api/guild/{rest_guild_id}/leave",
                headers=api_key_headers(rest_member_key),
            )
            mcp_leave = await leave_guild(mcp_member_key, mcp_guild_id)
            assert rest_leave.status_code == 200
            assert mcp_leave["ok"] is True
            assert _normalized_message(mcp_leave["message"]) == _normalized_message(rest_leave.json()["message"])

            rest_transport = await client.post(
                "/api/transport/create",
                headers=api_key_headers(rest_leader_key),
                json={
                    "from_region_id": 1,
                    "to_region_id": 2,
                    "items": {"RAT": 1},
                    "transport_type": "backpack",
                },
            )
            mcp_transport = await client.post(
                "/api/transport/create",
                headers=api_key_headers(mcp_leader_key),
                json={
                    "from_region_id": 1,
                    "to_region_id": 2,
                    "items": {"RAT": 1},
                    "transport_type": "backpack",
                },
            )
            assert rest_transport.status_code == 200
            assert mcp_transport.status_code == 200

            rest_contract = await client.post(
                "/api/warfare/contracts",
                headers=api_key_headers(rest_leader_key),
                json={
                    "mission_type": "raid_transport",
                    "target_region_id": 2,
                    "reward_per_agent": 100,
                    "max_agents": 1,
                    "target_transport_id": rest_transport.json()["transport_id"],
                },
            )
            mcp_contract = await create_contract(
                mcp_leader_key,
                mission_type="raid_transport",
                target_region_id=2,
                reward_per_agent=100,
                max_agents=1,
                target_transport_id=mcp_transport.json()["transport_id"],
            )
            assert rest_contract.status_code == 200
            assert mcp_contract["ok"] is True

            rest_enlist = await client.post(
                f"/api/warfare/contracts/{rest_contract.json()['contract_id']}/enlist",
                headers=api_key_headers(rest_member_key),
            )
            mcp_enlist = await contract_action_tool(
                mcp_member_key,
                action="enlist",
                contract_id=mcp_contract["contract"]["contract_id"],
            )
            assert rest_enlist.status_code == 200
            assert mcp_enlist["ok"] is True
            assert _normalized_message(mcp_enlist["message"]) == _normalized_message(rest_enlist.json()["message"])

            rest_cancel = await client.post(
                f"/api/warfare/contracts/{rest_contract.json()['contract_id']}/cancel",
                headers=api_key_headers(rest_leader_key),
            )
            mcp_cancel = await contract_action_tool(
                mcp_leader_key,
                action="cancel",
                contract_id=mcp_contract["contract"]["contract_id"],
            )
            assert rest_cancel.status_code == 200
            assert mcp_cancel["ok"] is True
            assert _normalized_message(mcp_cancel["message"]) == _normalized_message(rest_cancel.json()["message"])

    asyncio.run(scenario())


def test_rest_and_mcp_expose_equivalent_errors_on_key_negative_paths() -> None:
    async def scenario() -> None:
        async with seeded_client() as (client, _session_factory):
            agent = await register_agent("Parity Errors")
            assert agent["ok"] is True
            agent_key = agent["agent"]["api_key"]

            company_agent = await register_agent("Parity Company Errors")
            assert company_agent["ok"] is True
            company_agent_key = company_agent["agent"]["api_key"]
            created_company = await create_company(company_agent_key, "Parity Error Works")
            assert created_company["ok"] is True
            company_key = created_company["company"]["api_key"]

            rest_missing_company = await client.get(
                "/api/agent/company",
                headers=api_key_headers(agent_key),
            )
            mcp_missing_company = await get_company(agent_key)
            _assert_error_equivalent(rest_missing_company, mcp_missing_company)

            rest_missing_region = await client.get("/api/world/region/999")
            mcp_missing_region = await get_region_info(agent_key, region_id=999)
            _assert_error_equivalent(rest_missing_region, mcp_missing_region)

            rest_missing_intel = await client.get(
                "/api/intel/market/NOPE",
                headers=api_key_headers(agent_key),
            )
            mcp_missing_intel = await get_market_intel(agent_key, "NOPE")
            _assert_error_equivalent(rest_missing_intel, mcp_missing_intel)

            rest_missing_route = await client.get(
                "/api/intel/routes",
                headers=api_key_headers(agent_key),
                params={"to_region_id": 999},
            )
            mcp_missing_route = await get_route_intel(agent_key, to_region_id=999)
            _assert_error_equivalent(rest_missing_route, mcp_missing_route)

            rest_missing_recipe = await client.get(
                "/api/production/recipes",
                params={"building_type": "NOPE"},
            )
            mcp_missing_recipe = await get_recipes(company_key, building_type="NOPE")
            _assert_error_equivalent(rest_missing_recipe, mcp_missing_recipe)

            rest_missing_contract = await client.get("/api/warfare/contracts/999")
            mcp_missing_contract = await contract_action_tool(
                agent_key,
                action="get",
                contract_id=999,
            )
            _assert_error_equivalent(rest_missing_contract, mcp_missing_contract)

            owner = await register_agent("Parity Owner")
            intruder = await register_agent("Parity Intruder")
            assert owner["ok"] is True
            assert intruder["ok"] is True
            owner_key = owner["agent"]["api_key"]
            intruder_key = intruder["agent"]["api_key"]

            owner_transport = await client.post(
                "/api/transport/create",
                headers=api_key_headers(owner_key),
                json={
                    "from_region_id": 1,
                    "to_region_id": 2,
                    "items": {"RAT": 1},
                    "transport_type": "backpack",
                },
            )
            assert owner_transport.status_code == 200
            owner_transport_id = owner_transport.json()["transport_id"]

            created = await create_contract(
                owner_key,
                mission_type="raid_transport",
                target_region_id=2,
                reward_per_agent=100,
                max_agents=1,
                target_transport_id=owner_transport_id,
            )
            assert created["ok"] is True
            contract_id = created["contract"]["contract_id"]

            rest_forbidden_activate = await client.post(
                f"/api/warfare/contracts/{contract_id}/activate",
                headers=api_key_headers(intruder_key),
            )
            mcp_forbidden_activate = await contract_action_tool(
                intruder_key,
                action="activate",
                contract_id=contract_id,
            )
            _assert_error_equivalent(rest_forbidden_activate, mcp_forbidden_activate)

    asyncio.run(scenario())
