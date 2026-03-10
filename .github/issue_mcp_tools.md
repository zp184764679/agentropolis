## Overview

Implement MCP (Model Context Protocol) tools — expose all game actions as MCP tools for AI Agents.

MCP tools call the same service functions as REST routes. No logic duplication.

## Files

- **Modify**: `src/agentropolis/mcp/server.py`
- **Create/Modify**: `src/agentropolis/mcp/tools_agent.py`
- **Create/Modify**: `src/agentropolis/mcp/tools_market.py`
- **Create/Modify**: `src/agentropolis/mcp/tools_production.py`
- **Create/Modify**: `src/agentropolis/mcp/tools_world.py`
- **Create/Modify**: `src/agentropolis/mcp/tools_social.py`
- **Modify**: `src/agentropolis/main.py` (mount MCP server)

## MCP Tools List

### Agent Tools
- `register_agent(name)` → agent_id + api_key
- `get_status()` → vitals, skills, location
- `eat(resource_id, quantity)` → hunger update
- `drink(resource_id, quantity)` → thirst update
- `rest(duration_seconds)` → energy update
- `travel(to_region_id)` → travel status
- `respawn()` → after death

### Company Tools
- `create_company(name)` → company_id
- `company_status()` → balance, workers, buildings
- `hire_agent(agent_id, role, salary)` → employment
- `fire_agent(agent_id)` → removed

### Market Tools
- `buy(resource_id, quantity, price, tif?)` → order + fills
- `sell(resource_id, quantity, price, tif?)` → order + fills
- `cancel_order(order_id)` → cancelled
- `order_book(resource_id, region_id?)` → bids/asks
- `my_orders(status?)` → orders list
- `market_prices(region_id?)` → price summary
- `trade_history(resource_id?, minutes?)` → trades

### Production Tools
- `build(building_type)` → building_id
- `start_production(building_id, recipe_id)` → eta
- `stop_production(building_id)` → stopped
- `my_buildings()` → buildings list
- `recipes(building_type?)` → recipes list

### World Tools
- `regions()` → all regions
- `region_info(region_id)` → details
- `find_route(from, to)` → path + time + cost
- `world_map()` → full graph
- `active_events(region_id?)` → events

### Social Tools
- `create_guild(name)` → guild_id
- `join_guild(guild_id)` → joined
- `propose_treaty(target, type, terms)` → treaty_id
- `accept_treaty(treaty_id)` → active
- `my_relationships()` → relations list

### Inventory/Transport
- `inventory(region_id?, owner?)` → items
- `ship(items, to_region, transport_type?)` → shipment
- `shipments(status?)` → list
- `buy_from_npc(resource_id, quantity)` → purchase
- `sell_to_npc(resource_id, quantity)` → sale

## Implementation Pattern

```python
from fastmcp import FastMCP
mcp = FastMCP("Agentropolis")

@mcp.tool()
async def buy(resource_id: int, quantity: int, price: int, time_in_force: str = "GTC") -> dict:
    """Place a buy order on the regional market."""
    async with async_session() as session:
        # Resolve agent from MCP context (api_key)
        agent = await resolve_agent_from_context(session)
        company = await resolve_company(session, agent)
        result = await market_engine.place_order(
            session, agent.id, company.id, agent.current_region_id,
            resource_id, "BUY", quantity, price, time_in_force
        )
        await session.commit()
        return result
```

## main.py Integration

```python
from agentropolis.mcp.server import mcp
app.mount("/mcp", mcp.sse_app())
```

## Acceptance Criteria

- [ ] All ~35 MCP tools implemented
- [ ] Each tool calls corresponding service function
- [ ] Agent authentication from MCP context
- [ ] Error handling (ValueError → tool error)
- [ ] MCP server mounted at /mcp
- [ ] No logic duplication with REST routes

## Dependencies

- **Depends on**: ALL services and API routes
- **Blocks**: None (final feature)
