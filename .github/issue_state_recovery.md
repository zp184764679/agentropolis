## Overview

Proposed Issue `#87` — add state recovery and repair tooling for world operations.

When migrations, housekeeping, or world-state updates go wrong, operators need more than raw SQL.
This issue defines the minimum recovery toolkit for a persistent AI world.

## Files

- **Modify**: `src/agentropolis/cli.py`
- **Modify**: `alembic/`
- **Create/Modify**: `scripts/*`
- **Modify**: relevant `src/agentropolis/services/*`
- **Optional**: operator runbooks in `docs/`

## Scope

- snapshot / replay strategy
- backup / restore runbook
- repair / backfill scripts
- migration rollback constraints
- irreversible-change policy
- minimum incident recovery flow

## Non-Goals

- cross-region disaster recovery
- enterprise RPO/RTO commitments

## Acceptance Criteria

- [ ] There is at least one documented backup/restore path
- [ ] Operators can replay or recompute critical world state
- [ ] Repair/backfill scripts exist for common drift classes
- [ ] Migration safety boundaries are documented
- [ ] Data repair no longer depends on ad hoc manual SQL alone

## Dependencies

- **Depends on**: #16, #23, #37, Proposed #84
- **Blocks**: external rollout gate
