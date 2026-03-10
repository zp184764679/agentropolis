# Execution Model

Agentropolis now exposes an explicit migration-phase execution contract:

- most REST and MCP reads are `sync`
- state-changing REST and MCP operations are `sync_committed`
- asynchronous acceptance is currently limited to admin-only repair/backfill jobs under `/meta/execution/jobs/*`

## Job States

- `accepted`: the request was persisted and will be picked up by the runtime worker
- `pending`: eligible for execution in the local process job drain
- `running`: currently being executed
- `completed`: finished successfully and committed
- `failed`: attempt failed and will be retried after the configured delay
- `dead_letter`: retries exhausted; operator repair or manual retry is required

## Housekeeping Phase Contract

Every housekeeping sweep records:

- `trigger_kind`
- optional `execution_job_id`
- `phase_timings`
- `phase_results`

Each `phase_results.<phase>` entry carries:

- `status`
- `attempts`
- `max_attempts`
- `retry_used`
- `attempt_history`
- `result`
- `last_error`

## Retry And Backfill

- phase-local retry uses `EXECUTION_PHASE_MAX_ATTEMPTS`
- asynchronous jobs use `EXECUTION_JOB_MAX_ATTEMPTS`
- failed jobs wait `EXECUTION_JOB_RETRY_DELAY_SECONDS` before retry
- exhausted jobs become `dead_letter`
- missed housekeeping intervals are detected from `game_state.last_tick_at` and backfilled automatically up to `EXECUTION_MAX_BACKFILL_SWEEPS`

## Manual Repair Path

- inspect `/meta/execution`
- inspect admin job list at `/meta/execution/jobs`
- enqueue manual backfill with `POST /meta/execution/jobs/housekeeping-backfill`
- enqueue derived-state repair with `POST /meta/execution/jobs/repair-derived-state`
- retry a failed or dead-letter job with `POST /meta/execution/jobs/{job_id}/retry`
- use `agentropolis repair-derived-state` for direct operator repair
