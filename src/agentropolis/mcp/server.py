"""FastMCP server scaffold.

Current role:
- define the shared MCP application object
- document the intended REST/MCP service-layer parity
- provide a registration point for tool modules

Important:
- the external MCP transport and public contract are not frozen yet
- authentication/authorization semantics are still migrating from legacy scaffold rules
- this file should converge with the control-plane backlog before public rollout
"""

from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    "agentropolis",
    instructions=(
        "Agentropolis is an AI-native simulated world and control plane for LLM agents. "
        "Use the same world state through MCP and REST, and expect the contract surface "
        "to evolve toward agent-auth, regional actions, and shared service-layer parity."
    ),
)

# Tools are registered in tools_*.py modules via @mcp.tool() decorators.
# Import them here to trigger registration once the corresponding contract surface is ready.
# import agentropolis.mcp.tools_market  # noqa: F401
# import agentropolis.mcp.tools_production  # noqa: F401
# import agentropolis.mcp.tools_inventory  # noqa: F401
# import agentropolis.mcp.tools_company  # noqa: F401
# import agentropolis.mcp.tools_intel  # noqa: F401
