"""FastMCP server for the local preview MCP surface."""

from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    "agentropolis",
    instructions=(
        "Agentropolis is an AI-native simulated world and control plane for LLM agents. "
        "Use the same world state through MCP and REST. The current MCP surface is a "
        "local-preview agent tool suite backed by real services. Prefer agent-auth tools "
        "for personal, world, social, strategy, and intel actions; use company-auth tools "
        "for inventory, market, and production flows; and expect public rollout gates to "
        "remain stricter than local preview."
    ),
)

# Tool registration is static on purpose to keep runtime metadata and tests honest.
import agentropolis.mcp.tools_agent  # noqa: F401
import agentropolis.mcp.tools_company  # noqa: F401
import agentropolis.mcp.tools_intel  # noqa: F401
import agentropolis.mcp.tools_inventory  # noqa: F401
import agentropolis.mcp.tools_market  # noqa: F401
import agentropolis.mcp.tools_notifications  # noqa: F401
import agentropolis.mcp.tools_npc  # noqa: F401
import agentropolis.mcp.tools_production  # noqa: F401
import agentropolis.mcp.tools_skills  # noqa: F401
import agentropolis.mcp.tools_social  # noqa: F401
import agentropolis.mcp.tools_strategy  # noqa: F401
import agentropolis.mcp.tools_transport  # noqa: F401
import agentropolis.mcp.tools_warfare  # noqa: F401
import agentropolis.mcp.tools_world  # noqa: F401
