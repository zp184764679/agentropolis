## Overview

Proposed Issue `#86` — move economy balancing from scattered constants to governed tunables.

The world already has many balance-sensitive parameters. This issue creates the operational
discipline around them so live changes are reviewable, reversible, and measurable.

## Files

- **Modify**: `src/agentropolis/config.py`
- **Modify**: `src/agentropolis/services/economy_governance.py`
- **Add**: optional governance export helper under `scripts/`
- **Modify**: relevant `src/agentropolis/services/*`
- **Modify**: `tests/*` with economic regression scenarios

## Scope

- tunable parameter registry
- feature flags / staged rollout for balance changes
- balance-review checklist
- economic regression scenarios
- threshold definitions for source/sink, inflation, starvation, and volatility

## Non-Goals

- auto-balancing AI
- live-ops admin console

## Acceptance Criteria

- [ ] Core economic parameters have a central registry or documented source of truth
- [ ] Balance changes can be rolled out in stages
- [ ] At least one economic regression suite exists
- [ ] Major health thresholds are documented
- [ ] Parameter ownership is explicit enough to support review
- [ ] Governance snapshot can be exported or inspected without reading code directly

## Dependencies

- **Depends on**: #16, #23, #29, #38, Proposed #85
- **Blocks**: safe long-term live balancing
