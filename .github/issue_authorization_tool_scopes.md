## Overview

Proposed Issue `#82` — define authorization boundaries and tool scopes for the agent control plane.

Authentication alone is not enough. Agentropolis needs explicit actor/resource/action rules so that
REST routes and MCP tools expose only the intended power to each caller.

## Files

- **Modify**: `src/agentropolis/api/auth.py`
- **Modify**: `src/agentropolis/deps.py`
- **Modify**: `src/agentropolis/api/*.py`
- **Modify**: `src/agentropolis/mcp/*.py`
- **Optional**: `src/agentropolis/models/agent.py` or related models if scopes need persistence

## Scope

### Actor Model
- Agent
- Company
- Guild
- Admin / operator

### Rules To Define
- who owns which resources
- when an agent may act on behalf of a company
- which routes/tools require stronger scopes
- which operations are considered dangerous
- how permission denials are represented

### MCP-Specific Requirements
- tool scopes
- dangerous-operation gating
- parity with REST authz semantics

## Non-Goals

- full admin UI
- organization management backend
- complex RBAC editor

## Acceptance Criteria

- [ ] Actor/resource/action model is documented
- [ ] MCP tools do not default to full access with a single key
- [ ] Dangerous operations require explicit scoped permission
- [ ] Trading, production, transport, social, and admin-sensitive paths are covered
- [ ] Permission failures return stable errors
- [ ] Scope coverage tests exist

## Dependencies

- **Depends on**: #16, #30-#35, Proposed #81
- **Blocks**: Proposed #83, #88 and any external multi-agent rollout
