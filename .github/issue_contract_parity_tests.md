## Overview

Proposed Issue `#88` — lock REST/MCP parity with a dedicated contract test suite.

Agentropolis promises one shared service layer with two client surfaces. This issue makes that
promise enforceable in CI.

## Files

- **Create/Modify**: `tests/contract/*`
- **Modify**: `tests/e2e/*`
- **Modify**: `src/agentropolis/mcp/*`
- **Modify**: `src/agentropolis/api/*`

## Scope

- REST vs MCP parity tests
- auth scope coverage tests
- compatibility fixtures for external clients
- golden-path tests for trading, inventory, production, travel, notifications, strategy config
- smoke tests for OpenClaw-facing flows

## Non-Goals

- exhaustive UI tests
- broad fuzzing of every non-critical route

## Acceptance Criteria

- [ ] Main gameplay/control-plane paths are covered by parity tests
- [ ] Same logical action through REST and MCP yields the same state transition and equivalent errors
- [ ] Scope and permission failures are covered
- [ ] Contract-breaking changes fail CI clearly
- [ ] OpenClaw smoke tests reuse the same contract fixtures where possible

## Dependencies

- **Depends on**: Proposed #81, #82, #84, #85
- **Blocks**: external rollout gate
