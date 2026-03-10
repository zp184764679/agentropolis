# Recovery Runbook

Minimum local-preview recovery flow:

1. Export a world snapshot:

```bash
python scripts/export_world_snapshot.py --output openclaw/runtime/world-snapshot.before.json
```

2. Recompute derived economy state:

```bash
python scripts/repair_derived_state.py
```

3. Export a second snapshot:

```bash
python scripts/export_world_snapshot.py --output openclaw/runtime/world-snapshot.after.json
```

4. Compare:

- total currency supply
- current tick and latest housekeeping sweep
- company counts and top companies
- unread notifications and transport counts

Use this runbook for drift repair or after direct database interventions.
