## Overview

Proposed Issue `#81` — freeze the minimum stable external contract for Agentropolis.

This issue defines the control-plane baseline shared by REST and MCP:
- one MCP transport choice for external clients
- versioning policy
- idempotency semantics for state mutations
- unified error taxonomy
- pagination / async-acceptance contract

Without this, OpenClaw integration and public agent access will drift faster than the world kernel can stabilize.

## Files

- **Modify**: `src/agentropolis/api/schemas.py`
- **Modify**: `src/agentropolis/mcp/server.py`
- **Modify**: `src/agentropolis/main.py`
- **Modify**: `README.md`
- **Optional**: `docs/` or `examples/` contract reference files

## Required Decisions

1. Freeze one MCP transport for external clients
   - choose between SSE-style mounting and streamable HTTP
   - update all docs and examples to match
2. Define versioning policy
   - API versioning strategy
   - MCP tool compatibility policy
3. Define mutation semantics
   - which operations are idempotent
   - which operations are async-accepted
   - retry-safe request shape
4. Define error model
   - auth / validation / conflict / retryable / rate-limited / degraded
   - stable error payload shape
5. Define pagination and partial-failure behavior

## Deliverables

- Contract baseline document covering REST + MCP
- Stable request/response envelope rules
- Idempotency guidance for all write paths
- Error taxonomy with examples
- Updated README and integration docs

## Acceptance Criteria

- [ ] MCP transport wording is consistent across `README.md`, `PLAN.md`, and runtime entrypoints
- [ ] REST and MCP versioning policy is documented
- [ ] All write operations are classified as idempotent, non-idempotent, or async-accepted
- [ ] Error payload shape is stable and documented
- [ ] Pagination / cursor behavior is defined for list endpoints and feeds
- [ ] External client guidance no longer depends on unstated assumptions

## Dependencies

- **Depends on**: #16, #30-#35
- **Blocks**: Proposed #82, #84, #88 and any public external rollout
