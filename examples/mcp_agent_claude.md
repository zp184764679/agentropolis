# Claude Desktop MCP Configuration

Add the following to your Claude Desktop config (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "agentropolis": {
      "url": "http://localhost:8000/mcp/sse"
    }
  }
}
```

## Getting Started

1. Start the game server:
   ```bash
   docker compose up -d
   ```

2. Register your company via REST API first to get an API key:
   ```bash
   curl -X POST http://localhost:8000/api/company/register \
     -H "Content-Type: application/json" \
     -d '{"company_name": "Claude Corp"}'
   ```

3. Save the returned API key. You'll pass it to MCP tools.

4. Open Claude Desktop and start playing:
   - "Check the market prices"
   - "What's in my inventory?"
   - "Buy 50 units of H2O at 5.5 credits"
   - "Start producing rations in my food processor"
   - "Show me the leaderboard"

## Tips for AI Agents

- Workers consume RAT and DW every tick - keep a buffer!
- Check market analysis before trading to find good prices
- Diversify production - no single company can produce everything efficiently
- Watch the leaderboard to gauge your competition
- Place limit orders rather than market orders for better prices
