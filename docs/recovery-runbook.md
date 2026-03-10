# Recovery Runbook

Minimum local-preview recovery flow:

1. Export the recovery plan:

```bash
python scripts/export_recovery_plan.py --output openclaw/runtime/recovery-plan.json
```

2. Capture a before snapshot:

```bash
python scripts/export_world_snapshot.py --output openclaw/runtime/world-snapshot.before.json
```

3. Pick the repair mode:

- `python scripts/repair_derived_state.py`
  Use when balances, net worth, or inflation-derived state drift.
- `python scripts/replay_housekeeping.py --start-tick <N> --sweeps <K>`
  Use when periodic housekeeping work must be replayed in a controlled drill.
- `POST /meta/execution/jobs/housekeeping-backfill`
  Use when the runtime should accept an async backfill job instead of direct replay.

4. Capture an after snapshot:

```bash
python scripts/export_world_snapshot.py --output openclaw/runtime/world-snapshot.after.json
```

5. Compare:

- total currency supply
- current tick and latest housekeeping sweep
- open orders and transports in flight
- company counts and top companies
- unread notifications and pending execution jobs

## Backup / Restore Paths

- PostgreSQL runtime:
  - Backup: `pg_dump --format=custom --file backup.dump $DATABASE_URL`
  - Restore: `pg_restore --clean --if-exists --dbname $DATABASE_URL backup.dump`
- SQLite local preview:
  - Backup: copy the SQLite file before replay/repair work
  - Restore: replace the working SQLite file with the captured copy

## Safety Boundaries

- Always capture a world snapshot before destructive repair or replay work.
- Prefer restore-from-backup over down-migration after live data has already been mutated.
- Do not patch balances, inventories, or order state with ad hoc SQL unless you also capture before/after artifacts.
- Use housekeeping replay only during a maintenance window or isolated rehearsal environment.

## Irreversible Change Policy

- Dropping tables/columns or rewriting historical economic events requires a logical backup first.
- Bulk deletes and historical event rewrites are restore-only operations, not hotfix-by-SQL operations.
- Direct database repair must be documented with reason, operator, and before/after artifacts.
