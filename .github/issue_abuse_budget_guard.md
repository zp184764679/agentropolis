## Overview

Proposed Issue `#83` — add abuse, quota, and budget guardrails for continuously running AI agents.

Concurrency control prevents collapse under load, but it does not stop one bad client from
spamming tools, draining budgets, or putting the world into a degraded state. This issue adds
operational safety rails above the transport layer.

## Files

- **Modify**: `src/agentropolis/config.py`
- **Modify**: `src/agentropolis/deps.py`
- **Modify**: `src/agentropolis/main.py`
- **Modify**: `src/agentropolis/middleware/*`
- **Modify**: `src/agentropolis/services/*` where budget checks are enforced

## Scope

- per-agent quota
- per-tool quota
- optional per-IP quota for public ingress
- spending caps / budget exhaustion behavior
- kill switch for external AI access
- read-only / degraded mode
- denylist for unsafe operations

## Non-Goals

- full fraud platform
- reputation scoring system
- billing productization

## Acceptance Criteria

- [ ] Limits can be applied per agent and per tool
- [ ] Budget exhaustion blocks actions explicitly instead of failing silently
- [ ] There is a global external-access kill switch
- [ ] Read-only or degraded mode is documented and testable
- [ ] 429 / 403 / degraded-mode integration tests exist

## Dependencies

- **Depends on**: #78-#80, Proposed #82
- **Blocks**: public external rollout
