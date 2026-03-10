## Overview

Proposed Issue `#82` — define authorization boundaries and tool scopes for the agent control plane.

Authentication alone is not enough. Agentropolis needs explicit actor/resource/action rules so that
REST routes and MCP tools expose only the intended power to each caller.

## Current Repo Baseline

The repo now has a concrete baseline for this issue:

- `/meta/contract` publishes actor kinds, route/tool scope groups, dangerous operations, resource rules, and delegation rules
- `/meta/runtime` summarizes the current auth split plus authorization/delegation posture
- company-key market/production mutations inherit founder-agent preview policy budgets and deny rules
- cross-actor REST/MCP rejection coverage exists in `tests/test_authorization_scopes.py`

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
