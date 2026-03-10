# Local Preview Rollout Runbook

This runbook is for **closed-environment** Agentropolis preview operation only.
It is not the public rollout contract.

## 1. Start the stack

```bash
docker compose -f docker-compose.yml -f docker-compose.multi-agent.yml --profile preview-fleet up --build
```

## 2. Verify runtime surfaces

```bash
curl http://localhost:8000/health
curl http://localhost:8000/meta/runtime
curl http://localhost:8000/meta/observability
curl http://localhost:8000/meta/rollout-readiness
```

## 3. Export review artifacts

```bash
python scripts/export_contract_snapshot.py
python scripts/export_world_snapshot.py
python scripts/monitor_agents.py --manifest openclaw/runtime/agents.json --output openclaw/runtime/monitor-snapshot.json
```

## 4. Gate check

Capture rollout-readiness first, then review it together with the contract snapshot.

```bash
curl http://localhost:8000/meta/rollout-readiness > openclaw/runtime/rollout-readiness.json
python scripts/check_rollout_gate.py
```

## 5. Minimum operator review

- Confirm MCP transport is `streamable-http`
- Confirm tool count matches the static MCP registry
- Confirm blocking rollout failures are understood
- Confirm monitor snapshot and world snapshot were generated
- Confirm housekeeping is producing at least one recent sweep before trusting autonomy-driven activity

## 6. Recovery drill

```bash
python scripts/export_world_snapshot.py --output openclaw/runtime/world-snapshot.json
python scripts/repair_derived_state.py
```

If repair output changes derived state materially, export a second snapshot and compare before widening exposure.
