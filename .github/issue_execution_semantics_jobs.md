## Overview

Proposed Issue `#84` — make command and job execution semantics explicit.

Agentropolis mixes direct commands, housekeeping phases, retries, and periodic automation.
This issue defines when a command is considered accepted or complete, how failures are retried,
and how periodic work is observed and repaired.

## Files

- **Modify**: `src/agentropolis/services/game_engine.py`
- **Modify**: `src/agentropolis/main.py`
- **Modify**: `src/agentropolis/services/*` for task result envelopes
- **Add**: `src/agentropolis/services/execution_svc.py`
- **Add**: `src/agentropolis/api/execution.py`
- **Modify**: contract docs in `PLAN.md` / `docs/`

## Scope

- sync vs async command contract
- accepted / pending / completed / failed semantics
- retry / dedupe / dead-letter policy
- housekeeping phase result contract
- periodic task failure handling
- backfill policy for missed work

## Non-Goals

- adding a heavyweight workflow platform
- introducing a general-purpose distributed queue system

## Acceptance Criteria

- [x] The docs answer “when is this operation successful?”
- [x] Housekeeping phases expose explicit results, not just side effects
- [x] Failed periodic work has retry or manual-repair guidance
- [x] REST and MCP async semantics match
- [x] Backfill behavior is defined for missed or delayed periodic tasks

## Dependencies

- **Depends on**: #23, #39-#44, #50, #64-#71, Proposed #81
- **Blocks**: Proposed #85, #87, #88 and any stable async promise to external clients
