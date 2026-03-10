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

## Current Repo Baseline

- `tests/contract/test_rest_mcp_parity.py` covers mounted gameplay and preview route families
- `tests/e2e/test_rest_mcp_parity_journey.py` covers a mixed-surface playable journey
- `src/agentropolis/mcp/*` now includes REST-consistent error mapping for key `403/404 + error_code` paths

## Non-Goals

- exhaustive UI tests
- broad fuzzing of every non-critical route

## Acceptance Criteria

- [x] Main gameplay/control-plane paths are covered by parity tests
- [x] Same logical action through REST and MCP yields the same state transition and equivalent errors
- [x] Scope and permission failures are covered
- [x] Contract-breaking changes fail CI clearly
- [x] OpenClaw smoke tests reuse the same contract fixtures where possible

## Dependencies

- **Depends on**: Proposed #81, #82, #84, #85
- **Blocks**: external rollout gate
