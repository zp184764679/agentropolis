"""MCP tools for market operations (7 tools).

Tools:
- get_market_prices() — All resource prices + spread
- get_order_book(resource) — Bid/ask depth
- get_price_history(resource, ticks=50) — OHLCV candles
- place_buy_order(resource, quantity, price) — Submit buy
- place_sell_order(resource, quantity, price) — Submit sell
- cancel_order(order_id) — Cancel open order
- get_my_orders(status="OPEN") — List own orders

Each tool receives `api_key` as first parameter for authentication.
Use services layer for all business logic - do NOT duplicate.

Dependencies: services/market_engine.py, services/leaderboard.py
"""

# from agentropolis.mcp.server import mcp

# @mcp.tool()
# async def get_market_prices(api_key: str) -> str:
#     """Get current prices for all tradeable resources."""
#     raise NotImplementedError("Issue #13: Implement MCP market tools")
