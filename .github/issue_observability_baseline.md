## Overview

Proposed Issue `#85` — establish the minimum observability baseline for operating the world and control plane.

Today the repo has logging hooks, but that is not enough for a long-running AI-operated world.
This issue adds the metrics and visibility needed to debug agent behavior, world health, and
control-plane degradation.

## Files

- **Modify**: `src/agentropolis/main.py`
- **Modify**: `src/agentropolis/config.py`
- **Modify**: `src/agentropolis/middleware/metrics.py`
- **Modify**: `src/agentropolis/mcp/_shared.py`
- **Add**: `src/agentropolis/mcp/metrics.py`
- **Modify**: `src/agentropolis/services/game_engine.py`
- **Add**: `src/agentropolis/services/structured_logging.py`
- **Modify**: `src/agentropolis/services/*`
- **Optional**: monitoring export or dashboard helper files

## Scope

- structured logging
- request / MCP / housekeeping metrics
- slow request / slow MCP and lock contention visibility
- queue lag and periodic task latency
- economy health metrics
- autopilot and agent behavior metrics
- minimum alerting hooks

## Non-Goals

- full BI stack
- commercial analytics platform

## Acceptance Criteria

- [ ] Requests and background tasks emit structured context
- [ ] API error rate, MCP failure rate, housekeeping duration, execution lag, and lock contention are observable
- [ ] Economy health metrics cover at least source/sink, inflation, starvation, and stuck work signals
- [ ] There is a minimum dashboard or export path for external monitoring
- [ ] Rollout gates can reference real metrics instead of manual judgment only

## Dependencies

- **Depends on**: #23, #78-#80, Proposed #84
- **Blocks**: external rollout gate
