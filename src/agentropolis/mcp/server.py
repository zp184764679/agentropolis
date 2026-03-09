"""FastMCP server setup - mounted on FastAPI ASGI app.

Architecture:
- Single FastMCP instance with all 18 tools registered
- Tools call the same service layer as REST API (no duplication)
- MCP authentication: API key passed as tool parameter (first arg or context)
- Mounted at /mcp on the FastAPI app via ASGI

Implementation:
- Create FastMCP("agentropolis") instance
- Import and register all tools from tools_*.py modules
- Export `mcp_app` for mounting in main.py
"""

from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    "agentropolis",
    instructions=(
        "Agentropolis - AI Agent Economic Arena. "
        "You control a company in a competitive economy. "
        "Use market tools to trade resources, production tools to manufacture goods, "
        "and intel tools to analyze the market. Your workers need RAT (rations) and "
        "DW (drinking water) every tick or they'll become unhappy and leave."
    ),
)

# Tools are registered in tools_*.py modules via @mcp.tool() decorator.
# Import them here to trigger registration.
# Uncomment these imports after implementing the tool modules:
# import agentropolis.mcp.tools_market  # noqa: F401
# import agentropolis.mcp.tools_production  # noqa: F401
# import agentropolis.mcp.tools_inventory  # noqa: F401
# import agentropolis.mcp.tools_company  # noqa: F401
# import agentropolis.mcp.tools_intel  # noqa: F401
