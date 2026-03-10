"""FastMCP server for the local preview MCP surface."""

from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    "agentropolis",
    instructions=(
        "Agentropolis is an AI-native simulated world and control plane for LLM agents. "
        "Use the same world state through MCP and REST. The current MCP surface is a "
        "local-preview core tool suite backed by real services. Prefer agent-auth tools "
        "when available, keep company-auth explicit for legacy market/production/company "
        "operations, and expect public rollout gates to remain stricter than local preview."
    ),
)

# Tool registration is static on purpose to keep runtime metadata and tests honest.
import agentropolis.mcp.tools_agent  # noqa: F401
import agentropolis.mcp.tools_company  # noqa: F401
import agentropolis.mcp.tools_intel  # noqa: F401
import agentropolis.mcp.tools_inventory  # noqa: F401
import agentropolis.mcp.tools_market  # noqa: F401
import agentropolis.mcp.tools_production  # noqa: F401
import agentropolis.mcp.tools_world  # noqa: F401
