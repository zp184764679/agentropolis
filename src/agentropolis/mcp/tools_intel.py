"""MCP tools for intelligence/analytics (4 tools).

Tools:
- get_leaderboard(metric="net_worth") — Rankings
- get_game_status() — Current tick / timing / player count (no auth)
- get_trade_history(resource?, ticks=10) — Recent transactions
- get_market_analysis(resource) — Supply/demand/trend analysis

These are the KEY tools for AI decision-making.

Dependencies: services/leaderboard.py
"""

# from agentropolis.mcp.server import mcp
