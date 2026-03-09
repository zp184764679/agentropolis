"""MCP tools for production operations (5 tools).

Tools:
- get_buildings(api_key) — List owned buildings + status
- get_recipes(building_type?) — Available recipes
- start_production(api_key, building_id, recipe_id) — Begin manufacturing
- stop_production(api_key, building_id) — Halt production
- build_building(api_key, building_type) — Construct new facility

Dependencies: services/production.py
"""

# from agentropolis.mcp.server import mcp
